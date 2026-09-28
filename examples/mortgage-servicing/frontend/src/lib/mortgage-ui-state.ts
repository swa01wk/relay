export type CorrectionDraft = {
  mortgage_id?: string;
  effective_date?: string;
  proposed_rate?: number;
  current_rate?: number;
  projected_emi?: number;
  estimated_emi_delta?: number;
  current_emi?: number;
  status?: string;
};

export type MortgageUiState = {
  screen: "home" | "search_results" | "mortgage_case" | "rate_history" | "correction_draft";
  workflow: string | null;
  selected_entity: { type: string; id: string } | null;
  search_query: string | null;
  search_results: Array<Record<string, unknown>>;
  case_summary: Record<string, unknown> | null;
  rate_history: Array<Record<string, unknown>>;
  correction_draft: CorrectionDraft | null;
  activities: Array<{
    activity_id: string;
    label?: string;
    progress: number;
    status: "running" | "done";
  }>;
};

export function initialMortgageUiState(): MortgageUiState {
  return {
    screen: "home",
    workflow: null,
    selected_entity: null,
    search_query: null,
    search_results: [],
    case_summary: null,
    rate_history: [],
    correction_draft: null,
    activities: [],
  };
}

/** POC client-side projection when the operator edits draft fields (§10.3). */
export function recalculateDraftForEffectiveDate(
  draft: CorrectionDraft,
  effectiveDate: string,
): CorrectionDraft {
  const currentRate = Number(draft.current_rate ?? draft.proposed_rate ?? 0);
  const proposedRate = Number(draft.proposed_rate ?? currentRate);
  const emi = Number(draft.current_emi ?? 0);
  const deltaRate = Math.round((proposedRate - currentRate) * 1000) / 1000;
  const estimatedEmiDelta = Math.round((deltaRate / 0.125) * 12.0 * 100) / 100;
  const projectedEmi = Math.round((emi + estimatedEmiDelta) * 100) / 100;
  return {
    ...draft,
    effective_date: effectiveDate,
    projected_emi: projectedEmi,
    estimated_emi_delta: estimatedEmiDelta,
  };
}
