import { createActionGroup, emptyProps, props } from '@ngrx/store';
import { RunResult, TraceEvent } from '../../core/models';

export const RunMonitorActions = createActionGroup({
  source: 'Run Monitor',
  events: {
    Started: props<{ ticker: string }>(),
    Cancelled: emptyProps(),
  },
});

export const RunStreamActions = createActionGroup({
  source: 'Run Stream',
  events: {
    Retrying: props<{ attempt: number; delayMs: number }>(),
    Queued: props<{ message: string }>(),
    'Trace Received': props<{ event: TraceEvent }>(),
    Succeeded: props<{ result: RunResult }>(),
    Failed: props<{ error: string; kind: string }>(),
  },
});
