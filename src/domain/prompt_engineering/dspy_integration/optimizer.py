"""
DSPy integration for automatic prompt optimization.

This module wraps DSPy's built-in optimizers (MIPROv2, BootstrapFewShot)
to automatically optimize prompt instructions for LLM calls within the
LLM Platform.

Note: DSPy is an optional dependency. Graceful degradation when not installed.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Try importing DSPy - it's an optional dependency
try:
    import dspy
    HAS_DSPY = True
except ImportError:
    HAS_DSPY = False
    logger.warning("DSPy not installed. DSPyPromptOptimizer will operate in mock mode.")


class DSPyPromptOptimizer:
    """Optimize prompt instructions using DSPy's automatic prompt engineering.

    Supports:
    - MIPROv2: Instruction optimization via Bayesian optimization
    - BootstrapFewShot: Automatic few-shot example selection with rationale
    - Export: Extract optimized instructions for use in other templates
    """

    def __init__(self, lm: Optional[Any] = None):
        """Initialize optimizer.

        Args:
            lm: Optional DSPy language model. If not provided, uses dspy.LM if available.
        """
        self.lm = lm
        if HAS_DSPY and lm is None:
            try:
                self.lm = dspy.LM('openai/gpt-4o-mini')
            except Exception as e:
                logger.warning("Could not create default DSPy LM: %s", e)
        self._last_module: Optional[Any] = None
        self._last_instructions: Optional[str] = None
        logger.info("DSPyPromptOptimizer initialized (dspy_available=%s)", HAS_DSPY)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def optimize_with_miprov2(
        self,
        trainset: list[dict],
        metric,
        module_class: Optional[type] = None,
        num_threads: int = 4,
        max_bootstrapped_demos: int = 4,
        max_labeled_demos: int = 16,
        num_candidate_programs: int = 10,
    ) -> Any:
        """Optimize prompt instructions using MIPROv2.

        MIPROv2 (Multi-step Instruction PROposal) generates candidate
        instructions, evaluates them on the training set, and selects
        the best-performing one through Bayesian optimization.

        Args:
            trainset: List of training examples as dicts with 'question' and 'answer' keys.
            metric: DSPy metric function for evaluation.
            module_class: DSPy Module class (created dynamically if None).
            num_threads: Number of parallel evaluation threads.
            max_bootstrapped_demos: Max bootstrapped few-shot examples.
            max_labeled_demos: Max labeled few-shot examples.
            num_candidate_programs: Number of candidate programs to evaluate.

        Returns:
            Optimized DSPy module.
        """
        if not HAS_DSPY:
            logger.warning("DSPy not available, returning basic module")
            return self._mock_optimize(trainset)

        logger.info(
            "Starting MIPROv2 optimization with %d examples, "
            "threads=%d, bootstrapped_demos=%d, labeled_demos=%d, candidates=%d",
            len(trainset),
            num_threads,
            max_bootstrapped_demos,
            max_labeled_demos,
            num_candidate_programs,
        )

        try:
            # 1. Convert training dicts to dspy.Example objects
            dspy_examples = [
                dspy.Example(
                    question=ex.get("question", ""),
                    answer=ex.get("answer", ""),
                    context=ex.get("context", ""),
                ).with_inputs("question", "context")
                for ex in trainset
            ]

            # 2. Create or use the provided module class
            if module_class is None:
                module_class = self._create_qa_module()

            program = module_class()

            # 3. Configure and run MIPROv2 optimizer
            optimizer = dspy.MIPROv2(
                metric=metric,
                num_threads=num_threads,
                auto="light",
            )

            compiled_program = optimizer.compile(
                program,
                trainset=dspy_examples,
                max_bootstrapped_demos=max_bootstrapped_demos,
                max_labeled_demos=max_labeled_demos,
                num_candidate_programs=num_candidate_programs,
            )

            self._last_module = compiled_program
            logger.info("MIPROv2 optimization completed successfully")
            return compiled_program

        except Exception as e:
            logger.error("MIPROv2 optimization failed: %s", e, exc_info=True)
            logger.info("Falling back to mock module")
            return self._mock_optimize(trainset)

    def optimize_with_bootstrap(
        self,
        trainset: list[dict],
        metric,
        module_class: Optional[type] = None,
        max_bootstrapped_demos: int = 4,
        max_labeled_demos: int = 16,
        max_rounds: int = 1,
    ) -> Any:
        """Optimize prompts using BootstrapFewShot with rationale generation.

        BootstrapFewShot automatically generates few-shot examples with
        chain-of-thought rationales by running the model on training examples
        and selecting those where it succeeded.

        Args:
            trainset: List of training examples.
            metric: DSPy metric function.
            module_class: DSPy Module class.
            max_bootstrapped_demos: Max bootstrapped demonstrations.
            max_labeled_demos: Max labeled demonstrations.
            max_rounds: Bootstrap rounds.

        Returns:
            Optimized DSPy module.
        """
        if not HAS_DSPY:
            logger.warning("DSPy not available, returning basic module")
            return self._mock_optimize(trainset)

        logger.info(
            "Starting BootstrapFewShot optimization with %d examples, "
            "bootstrapped_demos=%d, labeled_demos=%d, rounds=%d",
            len(trainset),
            max_bootstrapped_demos,
            max_labeled_demos,
            max_rounds,
        )

        try:
            # 1. Convert training dicts to dspy.Example objects
            dspy_examples = [
                dspy.Example(
                    question=ex.get("question", ""),
                    answer=ex.get("answer", ""),
                    context=ex.get("context", ""),
                ).with_inputs("question", "context")
                for ex in trainset
            ]

            # 2. Create or use the provided module class
            if module_class is None:
                module_class = self._create_qa_module()

            program = module_class()

            # 3. Configure BootstrapFewShot with random seed
            optimizer = dspy.BootstrapFewShot(
                metric=metric,
                max_bootstrapped_demos=max_bootstrapped_demos,
                max_labeled_demos=max_labeled_demos,
                max_rounds=max_rounds,
            )

            # 4. Compile on trainset with metric
            compiled_program = optimizer.compile(
                program,
                trainset=dspy_examples,
            )

            self._last_module = compiled_program
            logger.info("BootstrapFewShot optimization completed successfully")
            return compiled_program

        except Exception as e:
            logger.error("BootstrapFewShot optimization failed: %s", e, exc_info=True)
            logger.info("Falling back to mock module")
            return self._mock_optimize(trainset)

    def export_prompt_instructions(self, module: Any) -> str:
        """Extract the optimized prompt instructions from a compiled DSPy module.

        Walks the module's predictors/signatures and collects all
        instruction fields into a formatted string.

        Args:
            module: Compiled DSPy module.

        Returns:
            Combined prompt instructions as a formatted string.
        """
        if not HAS_DSPY:
            if isinstance(module, dict) and "instruction" in module:
                return module["instruction"]
            return "DSPy not available - no instructions to export"

        try:
            parts: list[str] = []
            parts.append("=== Optimized Prompt Instructions ===\n")

            # Walk through the module's predictors
            predictors = []
            if hasattr(module, "named_predictors"):
                predictors = list(module.named_predictors())
            elif hasattr(module, "predictors"):
                predictors = module.predictors()

            for i, predictor in enumerate(predictors):
                parts.append(f"\n--- Predictor {i + 1} ---")

                # Extract signature information
                if hasattr(predictor, "signature"):
                    sig = predictor.signature
                    sig_name = getattr(sig, "signature", getattr(sig, "__name__", "Unknown"))
                    instruction = getattr(sig, "instructions", getattr(sig, "instruction", ""))
                    parts.append(f"Signature: {sig_name}")
                    parts.append(f"Instruction: {instruction}")

                    # Walk through input/output fields
                    if hasattr(sig, "input_fields"):
                        parts.append("Input fields:")
                        for name, field in sig.input_fields.items():
                            desc = getattr(field, "json_schema_extra", {}).get(
                                "__dspy_field_description", ""
                            ) if hasattr(field, "json_schema_extra") else ""
                            prefix = getattr(field, "prefix", "")
                            parts.append(f"  - {name}: prefix='{prefix}', desc='{desc}'")

                    if hasattr(sig, "output_fields"):
                        parts.append("Output fields:")
                        for name, field in sig.output_fields.items():
                            desc = getattr(field, "json_schema_extra", {}).get(
                                "__dspy_field_description", ""
                            ) if hasattr(field, "json_schema_extra") else ""
                            parts.append(f"  - {name}: desc='{desc}'")

                # Try extracting from the compiled program's demonstrations
                if hasattr(predictor, "demos") and predictor.demos:
                    parts.append(f"\nBootstrapped Demonstrations: {len(predictor.demos)}")
                    for j, demo in enumerate(predictor.demos[:3]):
                        parts.append(f"  Demo {j + 1}: {str(demo)[:200]}...")
                    if len(predictor.demos) > 3:
                        parts.append(f"  ... and {len(predictor.demos) - 3} more")

            compiled = "\n".join(parts)
            self._last_instructions = compiled
            logger.info("Exported prompt instructions (%d chars)", len(compiled))
            return compiled

        except Exception as e:
            logger.error("Failed to export prompt instructions: %s", e, exc_info=True)
            return f"Error exporting instructions: {e}"

    def export_instructions_from_last(self) -> str:
        """Export instructions from the last optimized module.

        Returns:
            Formatted instruction string, or empty string if no module cached.
        """
        if self._last_module is not None:
            return self.export_prompt_instructions(self._last_module)
        if self._last_instructions is not None:
            return self._last_instructions
        return ""

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _mock_optimize(self, trainset: list[dict]) -> dict:
        """Return a mock module when DSPy is not available.

        Contains the training examples and a placeholder answer function.
        """
        return {
            "examples": trainset[:10],
            "instruction": (
                "Answer the question based on the provided context. "
                "Be concise and accurate. If the context does not contain "
                "the answer, explicitly state that the information is not available."
            ),
            "answer": lambda question, context: (
                f"Based on context: {context[:200]}..."
            ),
            "is_mock": True,
        }

    def _create_qa_module(self) -> Any:
        """Create a basic QA/RAG DSPy module with signature.

        Returns a dspy.Module subclass instance configured for
        question-answering over retrieved context.

        Returns:
            A dspy.Module instance ready for compilation.
        """
        if not HAS_DSPY:
            return None

        try:
            # Define the RAG QA signature
            class GenerateAnswer(dspy.Signature):
                """Answer the question based on the provided context.

                Use only the information in the context to answer. If the
                context does not contain the answer, state that clearly.
                """

                context: str = dspy.InputField(
                    desc="Retrieved context passages relevant to the question"
                )
                question: str = dspy.InputField(
                    desc="The question to answer"
                )
                answer: str = dspy.OutputField(
                    desc="A concise, accurate answer grounded in the context"
                )

            # Define a simple RAG module
            class RAG(dspy.Module):
                def __init__(self):
                    super().__init__()
                    self.generate_answer = dspy.ChainOfThought(GenerateAnswer)

                def forward(self, question: str, context: str) -> Any:
                    prediction = self.generate_answer(
                        context=context, question=question
                    )
                    return dspy.Prediction(
                        answer=prediction.answer,
                        context=context,
                        question=question,
                    )

            logger.info("Created QA module with RAG signature")
            return RAG

        except Exception as e:
            logger.error("Failed to create QA module: %s", e, exc_info=True)
            # Fallback: create a minimal module using dspy.Predict
            try:

                class MinimalQA(dspy.Module):
                    def __init__(self):
                        super().__init__()
                        self.respond = dspy.Predict(
                            "context, question -> answer"
                        )

                    def forward(self, question: str, context: str) -> Any:
                        return self.respond(context=context, question=question)

                logger.info("Created minimal fallback QA module")
                return MinimalQA

            except Exception as e2:
                logger.error(
                    "Failed to create even minimal QA module: %s", e2, exc_info=True
                )
                return None
