'use client'

import { useEffect, useRef } from 'react'
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  CandlestickSeries,
  LineSeries,
  HistogramSeries,
  ColorType,
} from 'lightweight-charts'

type Bar = { time: string; open: number; high: number; low: number; close: number }
type LinePoint = { time: string; value: number }

type Mode = 'candles' | 'line' | 'histogram'

type Props = {
  data: Bar[] | LinePoint[]
  overlay?: LinePoint[]
  mode?: Mode
  height?: number
  /** Color for line/histogram mode. */
  color?: string
}

/**
 * Thin wrapper around TradingView's lightweight-charts.
 * Supports candles, line, and histogram (e.g. GEX, breadth).
 */
export function LightweightChart({
  data,
  overlay,
  mode = 'candles',
  height = 320,
  color = '#22c55e',
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)

  useEffect(() => {
    if (!containerRef.current) return

    const chart = createChart(containerRef.current, {
      height,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: 'rgba(255,255,255,0.7)',
        fontSize: 11,
      },
      grid: {
        vertLines: { color: 'rgba(255,255,255,0.06)' },
        horzLines: { color: 'rgba(255,255,255,0.06)' },
      },
      rightPriceScale: { borderColor: 'rgba(255,255,255,0.1)' },
      timeScale: { borderColor: 'rgba(255,255,255,0.1)', timeVisible: false },
      crosshair: { mode: 1 },
    })
    chartRef.current = chart

    let main: ISeriesApi<'Candlestick'> | ISeriesApi<'Line'> | ISeriesApi<'Histogram'>

    if (mode === 'candles') {
      main = chart.addSeries(CandlestickSeries, {
        upColor: '#22c55e',
        downColor: '#ef4444',
        borderUpColor: '#22c55e',
        borderDownColor: '#ef4444',
        wickUpColor: '#22c55e',
        wickDownColor: '#ef4444',
      })
      main.setData(data as Bar[])
    } else if (mode === 'line') {
      main = chart.addSeries(LineSeries, { color, lineWidth: 2 })
      main.setData(data as LinePoint[])
    } else {
      main = chart.addSeries(HistogramSeries, { color })
      main.setData(data as LinePoint[])
    }

    if (overlay && overlay.length > 0) {
      const ov = chart.addSeries(LineSeries, {
        color: 'rgba(245, 158, 11, 0.9)',
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      })
      ov.setData(overlay)
    }

    chart.timeScale().fitContent()

    const ro = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth })
      }
    })
    ro.observe(containerRef.current)

    return () => {
      ro.disconnect()
      chart.remove()
      chartRef.current = null
    }
  }, [data, overlay, mode, height, color])

  return <div ref={containerRef} className="w-full" style={{ height }} />
}
