import { ChevronLeft, ChevronRight } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { MONTHS } from '@/lib/roster'

export function shiftMonth(year: number, month: number, delta: number): [number, number] {
  const index = year * 12 + (month - 1) + delta
  return [Math.floor(index / 12), (index % 12) + 1]
}

export function MonthPicker({ year, month, onChange }: {
  year: number
  month: number
  onChange: (year: number, month: number) => void
}) {
  return (
    <div className="flex items-center gap-1" aria-label="Month">
      <Button variant="outline" size="icon-sm" aria-label="Previous month"
        onClick={() => onChange(...shiftMonth(year, month, -1))}>
        <ChevronLeft />
      </Button>
      <span className="min-w-36 text-center text-sm font-medium" data-testid="month-label">
        {MONTHS[month - 1]} {year}
      </span>
      <Button variant="outline" size="icon-sm" aria-label="Next month"
        onClick={() => onChange(...shiftMonth(year, month, 1))}>
        <ChevronRight />
      </Button>
    </div>
  )
}
