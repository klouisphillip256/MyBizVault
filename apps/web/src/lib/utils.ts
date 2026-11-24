import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function ugx(amount: number) {
  return `UGX ${new Intl.NumberFormat('en-UG').format(amount)}`
}
