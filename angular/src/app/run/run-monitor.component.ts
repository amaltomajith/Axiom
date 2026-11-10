import { Component, DestroyRef, inject, input } from '@angular/core';
import { takeUntilDestroyed, toObservable } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { Store } from '@ngrx/store';
import { filter, map } from 'rxjs';
import { RatingLabelPipe, RatingTonePipe } from '../core/format';
import { RunMonitorActions } from './state/run.actions';
import { runFeature } from './state/run.reducer';
import { selectRecentEvents, selectRunActive, selectRunSteps, selectRunTokens } from './state/run.selectors';

const TICKER = /^[A-Za-z][A-Za-z0-9.-]{0,9}$/;

@Component({
  selector: 'app-run-monitor',
  imports: [ReactiveFormsModule, RatingLabelPipe, RatingTonePipe],
  templateUrl: './run-monitor.component.html',
  styleUrl: './run-monitor.component.scss',
})
export class RunMonitor {
  /** prefilled from the `run/:ticker` deep link; a run never starts on its own (each one spends quota) */
  readonly ticker = input<string | undefined>();
  private readonly store = inject(Store);

  readonly tickerCtrl = new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.pattern(TICKER)] });
  readonly form = new FormGroup({ ticker: this.tickerCtrl });

  readonly status = this.store.selectSignal(runFeature.selectStatus);
  readonly runTicker = this.store.selectSignal(runFeature.selectTicker);
  readonly result = this.store.selectSignal(runFeature.selectResult);
  readonly error = this.store.selectSignal(runFeature.selectError);
  readonly errorKind = this.store.selectSignal(runFeature.selectErrorKind);
  readonly attempt = this.store.selectSignal(runFeature.selectAttempt);
  readonly retryInMs = this.store.selectSignal(runFeature.selectRetryInMs);
  readonly queueMessage = this.store.selectSignal(runFeature.selectQueueMessage);
  readonly active = this.store.selectSignal(selectRunActive);
  readonly steps = this.store.selectSignal(selectRunSteps);
  readonly recent = this.store.selectSignal(selectRecentEvents);
  readonly tokens = this.store.selectSignal(selectRunTokens);

  constructor() {
    toObservable(this.ticker)
      .pipe(
        filter((t): t is string => !!t),
        map(t => t.toUpperCase()),
        takeUntilDestroyed(),
      )
      .subscribe(t => this.tickerCtrl.setValue(t));

    // leaving the page stops the run, which closes its EventSource (see run.effects.ts)
    inject(DestroyRef).onDestroy(() => {
      if (this.active()) this.store.dispatch(RunMonitorActions.cancelled());
    });
  }

  start(): void {
    if (this.tickerCtrl.invalid) {
      this.tickerCtrl.markAsTouched();
      return;
    }
    this.store.dispatch(RunMonitorActions.started({ ticker: this.tickerCtrl.value.trim().toUpperCase() }));
  }

  cancel(): void {
    this.store.dispatch(RunMonitorActions.cancelled());
  }

  seconds(ms: number | null): number {
    return Math.max(1, Math.round((ms ?? 0) / 1000));
  }

  conviction(n: number): string {
    return `${Math.round(n * 100)}%`;
  }
}
