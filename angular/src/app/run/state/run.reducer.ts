import { createFeature, createReducer, on } from '@ngrx/store';
import { RunResult, TraceEvent } from '../../core/models';
import { RunMonitorActions, RunStreamActions } from './run.actions';

export type RunStatus = 'idle' | 'connecting' | 'retrying' | 'queued' | 'running' | 'done' | 'error' | 'cancelled';

export const ACTIVE_STATUSES: readonly RunStatus[] = ['connecting', 'retrying', 'queued', 'running'];

export interface RunState {
  ticker: string | null;
  status: RunStatus;
  events: TraceEvent[];
  result: RunResult | null;
  error: string | null;
  errorKind: string | null;
  queueMessage: string | null;
  attempt: number;
  retryInMs: number | null;
}

export const initialState: RunState = {
  ticker: null,
  status: 'idle',
  events: [],
  result: null,
  error: null,
  errorKind: null,
  queueMessage: null,
  attempt: 0,
  retryInMs: null,
};

export const reducer = createReducer(
  initialState,
  on(RunMonitorActions.started, (_s, { ticker }): RunState => ({ ...initialState, ticker, status: 'connecting' })),
  on(RunMonitorActions.cancelled, (s): RunState => (ACTIVE_STATUSES.includes(s.status) ? { ...s, status: 'cancelled', retryInMs: null } : s)),
  on(RunStreamActions.retrying, (s, { attempt, delayMs }): RunState => ({ ...s, status: 'retrying', attempt, retryInMs: delayMs })),
  on(RunStreamActions.queued, (s, { message }): RunState => ({ ...s, status: 'queued', queueMessage: message, retryInMs: null })),
  on(RunStreamActions.traceReceived, (s, { event }): RunState => ({
    ...s,
    status: 'running',
    events: [...s.events, event],
    retryInMs: null,
  })),
  on(RunStreamActions.succeeded, (s, { result }): RunState => ({ ...s, status: 'done', result, retryInMs: null })),
  on(RunStreamActions.failed, (s, { error, kind }): RunState => ({ ...s, status: 'error', error, errorKind: kind, retryInMs: null })),
);

export const runFeature = createFeature({ name: 'run', reducer });
