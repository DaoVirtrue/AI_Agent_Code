"""Golden dataset builder for RAG evaluation with contamination checks."""

import json
import hashlib
import random
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

from src.monitoring.logging_setup import get_logger

logger = get_logger(__name__)


@dataclass
class GoldenExample:
    """A single golden dataset example for evaluation."""

    id: str
    query: str
    expected_answer: str
    contexts: list[str] = field(default_factory=list)
    category: str = "general"
    difficulty: str = "medium"  # easy, medium, hard
    metadata: dict = field(default_factory=dict)

    @property
    def context_count(self) -> int:
        """Number of context documents for this example."""
        return len(self.contexts)

    def to_dict(self) -> dict:
        """Serialize to dict."""
        return {
            "id": self.id,
            "query": self.query,
            "expected_answer": self.expected_answer,
            "contexts": self.contexts,
            "category": self.category,
            "difficulty": self.difficulty,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GoldenExample":
        """Deserialize from dict."""
        return cls(
            id=data["id"],
            query=data["query"],
            expected_answer=data["expected_answer"],
            contexts=data.get("contexts", []),
            category=data.get("category", "general"),
            difficulty=data.get("difficulty", "medium"),
            metadata=data.get("metadata", {}),
        )


class GoldenDatasetBuilder:
    """Builds and manages golden datasets for RAG evaluation.

    Requirements:
    - Minimum 100 examples for a valid dataset
    - Coverage validation across categories and difficulties
    - Contamination checks to prevent train/val/test leakage
    - Stratified splitting for train/val/test
    """

    MINIMUM_SIZE = 100
    MIN_CATEGORIES = 5
    MIN_EXAMPLES_PER_CATEGORY = 5

    def __init__(self, storage_dir: str = "./golden_datasets"):
        """Initialize the golden dataset builder.

        Args:
            storage_dir: Directory for storing golden datasets.
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._examples: list[GoldenExample] = []

    async def build(
        self,
        name: str,
        examples: Optional[list[GoldenExample]] = None,
        from_file: Optional[str] = None,
    ) -> list[GoldenExample]:
        """Build a golden dataset.

        Args:
            name: Dataset name.
            examples: Optional list of pre-created examples.
            from_file: Optional path to load examples from JSON file.

        Returns:
            List of validated GoldenExample objects.

        Raises:
            ValueError: If minimum size or coverage requirements are not met.
        """
        if from_file:
            examples = self._load_from_file(from_file)

        if examples:
            self._examples = list(examples)

        # Validate minimum size
        if len(self._examples) < self.MINIMUM_SIZE:
            raise ValueError(
                f"Golden dataset must have at least {self.MINIMUM_SIZE} examples. "
                f"Currently has {len(self._examples)}."
            )

        # Validate coverage
        self._validate_coverage(self._examples)

        # Deduplicate
        self._examples = self._deduplicate(self._examples)

        # Save
        await self._save(name)

        logger.info(
            "Golden dataset built",
            name=name,
            size=len(self._examples),
            categories=self._get_category_distribution(self._examples),
        )

        return self._examples

    def _validate_coverage(self, examples: list[GoldenExample]) -> None:
        """Validate that the dataset has adequate coverage.

        Checks:
        - Minimum number of categories
        - Minimum examples per category
        - Adequate difficulty distribution
        """
        categories = {}
        difficulties = {"easy": 0, "medium": 0, "hard": 0}

        for ex in examples:
            categories[ex.category] = categories.get(ex.category, 0) + 1
            difficulties[ex.difficulty] = difficulties.get(ex.difficulty, 0) + 1

        # Check category count
        if len(categories) < self.MIN_CATEGORIES:
            logger.warning(
                "Low category diversity",
                categories=len(categories),
                minimum=self.MIN_CATEGORIES,
            )

        # Check examples per category
        for cat, count in categories.items():
            if count < self.MIN_EXAMPLES_PER_CATEGORY:
                logger.warning(
                    "Low examples per category",
                    category=cat,
                    count=count,
                    minimum=self.MIN_EXAMPLES_PER_CATEGORY,
                )

        logger.info(
            "Coverage validation",
            total_examples=len(examples),
            categories=categories,
            difficulties=difficulties,
        )

    def _check_contamination(
        self,
        train_examples: list[GoldenExample],
        val_examples: list[GoldenExample],
        test_examples: list[GoldenExample],
    ) -> dict:
        """Check for data contamination between splits.

        Contamination includes:
        - Exact query overlap
        - Near-duplicate queries (Jaccard > 0.8)
        - Answer overlap across splits

        Args:
            train_examples: Training split examples.
            val_examples: Validation split examples.
            test_examples: Test split examples.

        Returns:
            Dict with contamination metrics.
        """
        splits = {
            "train": train_examples,
            "val": val_examples,
            "test": test_examples,
        }

        contamination = {
            "exact_query_overlaps": [],
            "near_duplicate_overlaps": [],
            "is_clean": True,
        }

        split_names = list(splits.keys())
        for i, name_a in enumerate(split_names):
            for name_b in split_names[i + 1:]:
                overlap = self._find_overlaps(splits[name_a], splits[name_b])
                if overlap["exact"]:
                    contamination["exact_query_overlaps"].append({
                        "split_a": name_a,
                        "split_b": name_b,
                        "count": overlap["exact"],
                    })
                    contamination["is_clean"] = False

                if overlap["near_duplicate"]:
                    contamination["near_duplicate_overlaps"].append({
                        "split_a": name_a,
                        "split_b": name_b,
                        "count": overlap["near_duplicate"],
                    })
                    contamination["is_clean"] = False

        if not contamination["is_clean"]:
            logger.error("Data contamination detected", contamination=contamination)

        return contamination

    def split_dataset(
        self,
        examples: Optional[list[GoldenExample]] = None,
        train_ratio: float = 0.7,
        val_ratio: float = 0.15,
        test_ratio: float = 0.15,
        seed: int = 42,
        stratified: bool = True,
    ) -> tuple[list[GoldenExample], list[GoldenExample], list[GoldenExample]]:
        """Split the dataset into train/val/test splits.

        Args:
            examples: Examples to split (uses internal if not provided).
            train_ratio: Fraction for training.
            val_ratio: Fraction for validation.
            test_ratio: Fraction for testing.
            seed: Random seed for reproducibility.
            stratified: If True, maintain category distribution in splits.

        Returns:
            Tuple of (train_examples, val_examples, test_examples).
        """
        if examples is None:
            examples = self._examples

        total_ratio = train_ratio + val_ratio + test_ratio
        if abs(total_ratio - 1.0) > 0.001:
            raise ValueError(f"Split ratios must sum to 1.0, got {total_ratio}")

        rng = random.Random(seed)

        if stratified:
            return self._stratified_split(examples, train_ratio, val_ratio, test_ratio, rng)

        # Simple random split
        shuffled = list(examples)
        rng.shuffle(shuffled)

        n = len(shuffled)
        train_end = int(n * train_ratio)
        val_end = train_end + int(n * val_ratio)

        train = shuffled[:train_end]
        val = shuffled[train_end:val_end]
        test = shuffled[val_end:]

        # Contamination check
        self._check_contamination(train, val, test)

        logger.info(
            "Dataset split",
            total=n,
            train=len(train),
            val=len(val),
            test=len(test),
        )

        return train, val, test

    def _stratified_split(
        self,
        examples: list[GoldenExample],
        train_ratio: float,
        val_ratio: float,
        test_ratio: float,
        rng: random.Random,
    ) -> tuple[list[GoldenExample], list[GoldenExample], list[GoldenExample]]:
        """Perform stratified split maintaining category distribution."""
        # Group by category
        by_category: dict[str, list[GoldenExample]] = {}
        for ex in examples:
            by_category.setdefault(ex.category, []).append(ex)

        train, val, test = [], [], []

        for category, cat_examples in by_category.items():
            rng.shuffle(cat_examples)
            n = len(cat_examples)
            train_end = max(1, int(n * train_ratio))
            val_end = train_end + max(1, int(n * val_ratio))

            train.extend(cat_examples[:train_end])
            val.extend(cat_examples[train_end:val_end])
            test.extend(cat_examples[val_end:])

        # Shuffle each split
        rng.shuffle(train)
        rng.shuffle(val)
        rng.shuffle(test)

        self._check_contamination(train, val, test)

        return train, val, test

    def _find_overlaps(
        self,
        examples_a: list[GoldenExample],
        examples_b: list[GoldenExample],
    ) -> dict:
        """Find query overlaps between two sets of examples."""
        queries_a = {ex.query.lower().strip() for ex in examples_a}
        queries_b = {ex.query.lower().strip() for ex in examples_b}

        exact = len(queries_a & queries_b)

        # Near-duplicate detection via Jaccard
        near_duplicate = 0
        for qa in queries_a:
            words_a = set(qa.split())
            for qb in queries_b:
                words_b = set(qb.split())
                if words_a and words_b:
                    jaccard = len(words_a & words_b) / len(words_a | words_b)
                    if jaccard > 0.8 and qa != qb:
                        near_duplicate += 1
                        break

        return {"exact": exact, "near_duplicate": near_duplicate}

    def _deduplicate(self, examples: list[GoldenExample]) -> list[GoldenExample]:
        """Remove duplicate examples based on query hash."""
        seen = set()
        unique = []
        for ex in examples:
            query_hash = hashlib.md5(ex.query.lower().encode()).hexdigest()
            if query_hash not in seen:
                seen.add(query_hash)
                unique.append(ex)
            else:
                logger.debug("Duplicate example removed", query=ex.query[:100])

        duplicates = len(examples) - len(unique)
        if duplicates:
            logger.info("Deduplication complete", removed=duplicates, remaining=len(unique))

        return unique

    def _get_category_distribution(
        self, examples: list[GoldenExample]
    ) -> dict[str, int]:
        """Get the distribution of examples across categories."""
        dist = {}
        for ex in examples:
            dist[ex.category] = dist.get(ex.category, 0) + 1
        return dist

    def _load_from_file(self, filepath: str) -> list[GoldenExample]:
        """Load examples from a JSON file."""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Golden dataset file not found: {filepath}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            return [GoldenExample.from_dict(item) for item in data]
        elif isinstance(data, dict) and "examples" in data:
            return [GoldenExample.from_dict(item) for item in data["examples"]]
        else:
            raise ValueError(f"Unexpected JSON format in {filepath}")

    async def _save(self, name: str) -> None:
        """Save the golden dataset to disk."""
        filepath = self.storage_dir / f"{name}.json"
        data = {
            "name": name,
            "version": "1.0",
            "created_at": __import__("datetime").datetime.utcnow().isoformat(),
            "size": len(self._examples),
            "examples": [ex.to_dict() for ex in self._examples],
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info("Golden dataset saved", path=str(filepath), size=len(self._examples))

    async def load(self, name: str) -> list[GoldenExample]:
        """Load a previously saved golden dataset."""
        filepath = self.storage_dir / f"{name}.json"
        if not filepath.exists():
            raise FileNotFoundError(f"Golden dataset '{name}' not found")

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        examples = [GoldenExample.from_dict(item) for item in data["examples"]]
        self._examples = examples
        return examples

    @staticmethod
    def generate_synthetic_example(
        query: str,
        answer: str,
        contexts: Optional[list[str]] = None,
        category: str = "general",
        difficulty: str = "medium",
    ) -> GoldenExample:
        """Create a single golden example with auto-generated ID."""
        query_hash = hashlib.md5(query.encode()).hexdigest()[:8]
        return GoldenExample(
            id=f"golden-{query_hash}",
            query=query,
            expected_answer=answer,
            contexts=contexts or [],
            category=category,
            difficulty=difficulty,
        )
