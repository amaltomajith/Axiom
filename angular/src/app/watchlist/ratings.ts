import { RatingInfo, ThesisRow } from '../core/models';

/** Latest rating per ticker. The API returns theses newest first, so the first row per ticker wins. */
export function latestRatings(rows: ThesisRow[]): Record<string, RatingInfo> {
  const out: Record<string, RatingInfo> = {};
  for (const r of rows) {
    if (!out[r.ticker]) out[r.ticker] = { rating: r.rating, conviction: r.conviction, issuedOn: r.issue_date };
  }
  return out;
}
