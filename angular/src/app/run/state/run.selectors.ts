import { createSelector } from '@ngrx/store';
import { deriveSteps } from '../steps';
import { ACTIVE_STATUSES, runFeature } from './run.reducer';

export const selectRunState = runFeature.selectRunState;
export const selectRunStatus = runFeature.selectStatus;
export const selectRunTicker = runFeature.selectTicker;
export const selectRunResult = runFeature.selectResult;
export const selectRunError = runFeature.selectError;

export const selectRunActive = createSelector(selectRunStatus, status => ACTIVE_STATUSES.includes(status));

export const selectRunSteps = createSelector(runFeature.selectEvents, selectRunStatus, deriveSteps);

/** The newest events first, for the live log. */
export const selectRecentEvents = createSelector(runFeature.selectEvents, events => events.slice(-12).reverse());

export const selectRunTokens = createSelector(runFeature.selectEvents, events =>
  events
    .filter(e => e.type === 'llm_call' && !e.data['cached'])
    .reduce((sum, e) => sum + Number(e.data['prompt_tokens'] ?? 0) + Number(e.data['completion_tokens'] ?? 0), 0),
);
