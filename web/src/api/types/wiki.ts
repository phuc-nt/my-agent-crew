/** A page as the list shows it: enough to choose one, without its body. */
export interface WikiPageSummary {
  slug: string;
  kind: string;
  title: string;
  status: string;
  updated: string;
  sources: string[];
  question_count: number;
}

export interface WikiPage extends Omit<WikiPageSummary, "question_count"> {
  body: string;
  questions: string[];
}

/** Only the fields being changed; what is left out keeps its current value. */
export interface WikiPageEdit {
  title?: string;
  body?: string;
  sources?: string[];
  questions?: string[];
  status?: string;
}

export interface WikiList {
  pages: WikiPageSummary[];
  kinds: string[];
  count: number;
}

export interface WikiProblem {
  slug: string;
  kind: string;
  detail: string;
}

export interface WikiReport {
  problems: WikiProblem[];
  questions: { slug: string; question: string }[];
}
