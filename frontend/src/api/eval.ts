import client from './client';

export interface EvalRequest {
  queries: string[];
  expected_answers?: string[];
  metrics?: string[];
  top_k?: number;
  retrieval_strategy?: string;
}

export interface EvalResult {
  faithfulness: number;
  answer_relevancy: number;
  context_precision: number;
  context_recall: number;
  answer_correctness?: number | null;
  overall_score: number;
  num_queries: number;
  run_id?: string;
  per_query?: EvalPerQuery[];
}

export interface EvalPerQuery {
  query: string;
  generated_answer: string;
  retrieved_contexts: string[];
  expected_answer?: string | null;
  scores: {
    faithfulness: number;
    answer_relevancy: number;
    context_precision: number;
    context_recall: number;
    answer_correctness?: number | null;
    overall: number;
  };
}

export async function runEvaluation(request: EvalRequest): Promise<EvalResult> {
  const response = await client.post<EvalResult>('/v1/rag/evaluate', request);
  return response.data;
}

export async function listEvalRuns(limit = 50): Promise<{ items: any[]; total: number }> {
  const response = await client.get('/v1/rag/evaluate/runs', { params: { limit } });
  return response.data;
}

export async function getEvalRun(runId: string): Promise<any> {
  const response = await client.get(`/v1/rag/evaluate/runs/${runId}`);
  return response.data;
}
