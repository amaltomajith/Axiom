import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Observable } from 'rxjs';
import { TestScheduler } from 'rxjs/testing';
import { ApiService } from './api.service';
import { ApiStatusService } from './api-status.service';
import { BACKOFF } from './backoff';
import { API_BASE } from './config';
import { Health } from './models';

const HEALTH: Health = { ok: true, llm_chain: ['groq'], auth_required: true, storage: 'postgres', daily_cap: 40 };

describe('ApiStatusService', () => {
  it('shares one health request between every subscriber (shareReplay)', () => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), { provide: API_BASE, useValue: 'http://api' }],
    });
    const status = TestBed.inject(ApiStatusService);
    const http = TestBed.inject(HttpTestingController);
    const got: Health[] = [];

    status.ready$.subscribe(h => got.push(h));
    status.ready$.subscribe(h => got.push(h));
    status.status$.subscribe();

    http.expectOne('http://api/api/health').flush(HEALTH); // exactly one request for three subscribers
    status.ready$.subscribe(h => got.push(h)); // a late subscriber gets the replayed value
    http.verify();
    expect(got).toEqual([HEALTH, HEALTH, HEALTH]);
  });

  describe('status$ (marbles)', () => {
    let scheduler: TestScheduler;
    beforeEach(() => (scheduler = new TestScheduler((a, e) => expect(a).toEqual(e))));

    function withHealth(health: () => Observable<Health>): ApiStatusService {
      TestBed.configureTestingModule({
        providers: [
          { provide: ApiService, useValue: { health } },
          { provide: BACKOFF, useValue: (n: number) => n * 1000 },
        ],
      });
      return TestBed.inject(ApiStatusService);
    }

    it('says ready straight away when the API answers fast', () => {
      scheduler.run(({ cold, expectObservable }) => {
        const status = withHealth(() => cold('100ms (h|)', { h: HEALTH }));
        expectObservable(status.status$).toBe('c 99ms (r|)', { c: 'checking', r: 'ready' });
      });
    });

    it('says waking after 2.5 s, then ready, when the API is slow to start', () => {
      scheduler.run(({ cold, expectObservable }) => {
        const status = withHealth(() => cold('4000ms (h|)', { h: HEALTH }));
        expectObservable(status.status$).toBe('c 2499ms w 1499ms (r|)', { c: 'checking', w: 'waking', r: 'ready' });
      });
    });

    it('retries with backoff and says unreachable only after every retry failed', () => {
      scheduler.run(({ cold, expectObservable }) => {
        let calls = 0;
        const status = withHealth(() => (calls++, cold('10ms #')));
        // 6 attempts of 10 ms, waits of 1+2+3+4+5 s between them: the last fails at 15060 ms
        expectObservable(status.status$).toBe('c 2499ms w 12559ms (u|)', { c: 'checking', w: 'waking', u: 'unreachable' });
        scheduler.flush();
        expect(calls).toBe(6);
      });
    });
  });
});
