import * as React from 'react'
import { cn } from '@/lib/utils'

export interface SliderProps {
  className?: string
  value?: number[]
  defaultValue?: number[]
  min?: number
  max?: number
  step?: number
  onValueChange?: (value: number[]) => void
  disabled?: boolean
}

export const Slider = React.forwardRef<HTMLInputElement, SliderProps>(
  ({ className, value, defaultValue, min = 0, max = 100, step = 1, onValueChange, disabled }, ref) => {
    const val = value?.[0] ?? defaultValue?.[0] ?? min
    return (
      <div className={cn('relative flex w-full touch-none select-none items-center', className)}>
        <input
          ref={ref}
          type="range"
          min={min}
          max={max}
          step={step}
          value={val}
          disabled={disabled}
          onChange={(e) => onValueChange?.([parseFloat(e.target.value)])}
          className="w-full h-2 bg-dark-200 rounded-lg appearance-none cursor-pointer dark:bg-dark-700 accent-primary-600"
        />
      </div>
    )
  }
)
Slider.displayName = 'Slider'