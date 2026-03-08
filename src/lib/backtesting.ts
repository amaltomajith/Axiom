import { OHLCVData, generateHistoricalData } from './stockData';
import { runPredictions, PredictionResult } from './models';

export interface BacktestResult {
  model: string;
  rmse: number;
  directionalAccuracy: number;
  predictedPrices: number[];
  actualPrices: number[];
  dates: string[];
  color: string;
}

export function runBacktestFromData(fullData: OHLCVData[]): BacktestResult[] {
  const splitIndex = Math.max(fullData.length - 14, 30);
  const trainData = fullData.slice(0, splitIndex);
  const testData = fullData.slice(splitIndex, splitIndex + 14);

  if (trainData.length < 20 || testData.length < 5) {
    return [];
  }

  const predictions = runPredictions(trainData, testData.length);
  const actualPrices = testData.map(d => d.close);
  const dates = testData.map(d => d.date);

  return predictions.map(pred => {
    const preds = pred.predictions.slice(0, actualPrices.length);
    const mse = preds.reduce((sum, p, i) => sum + Math.pow(p - actualPrices[i], 2), 0) / preds.length;
    const rmse = Math.sqrt(mse);

    let correctDir = 0;
    for (let i = 1; i < Math.min(preds.length, actualPrices.length); i++) {
      const predDir = preds[i] > preds[i - 1];
      const actDir = actualPrices[i] > actualPrices[i - 1];
      if (predDir === actDir) correctDir++;
    }
    const directionalAccuracy = preds.length > 1 ? correctDir / (Math.min(preds.length, actualPrices.length) - 1) : 0;

    return {
      model: pred.model,
      rmse: +rmse.toFixed(2),
      directionalAccuracy: +(directionalAccuracy * 100).toFixed(1),
      predictedPrices: preds,
      actualPrices,
      dates,
      color: pred.color,
    };
  });
}

export function runBacktest(ticker: string, startDate: Date): BacktestResult[] {
  // Legacy fallback using mock data
  const endDate = new Date(startDate);
  endDate.setDate(endDate.getDate() + 60);
  const fullData = generateHistoricalData(ticker, 90, endDate);
  return runBacktestFromData(fullData);
}
