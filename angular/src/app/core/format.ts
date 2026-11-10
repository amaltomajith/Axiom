import { Pipe, PipeTransform } from '@angular/core';
import { Rating } from './models';

const RATING_LABEL: Record<Rating, string> = {
  STRONG_BUY: 'Strong buy',
  BUY: 'Buy',
  HOLD: 'Hold',
  SELL: 'Sell',
  STRONG_SELL: 'Strong sell',
  NO_CALL: 'No call',
};

export function ratingLabel(r: Rating | null | undefined): string {
  return r ? RATING_LABEL[r] : 'Not rated';
}

/** CSS class for a rating pill: semantic colour only (gain, loss, caution), never decoration. */
export function ratingTone(r: Rating | null | undefined): string {
  if (r === 'BUY' || r === 'STRONG_BUY') return 'buy';
  if (r === 'SELL' || r === 'STRONG_SELL') return 'sell';
  if (r === 'HOLD') return 'hold';
  return '';
}

export function formatPct(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return 'n/a';
  return `${n > 0 ? '+' : ''}${n.toFixed(digits)}%`;
}

export function formatPrice(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return 'n/a';
  return n.toLocaleString('en-US', { style: 'currency', currency: 'USD' });
}

@Pipe({ name: 'pct' })
export class PctPipe implements PipeTransform {
  transform(n: number | null | undefined, digits = 2): string {
    return formatPct(n, digits);
  }
}

@Pipe({ name: 'price' })
export class PricePipe implements PipeTransform {
  transform(n: number | null | undefined): string {
    return formatPrice(n);
  }
}

@Pipe({ name: 'ratingLabel' })
export class RatingLabelPipe implements PipeTransform {
  transform(r: Rating | null | undefined): string {
    return ratingLabel(r);
  }
}

@Pipe({ name: 'ratingTone' })
export class RatingTonePipe implements PipeTransform {
  transform(r: Rating | null | undefined): string {
    return ratingTone(r);
  }
}
