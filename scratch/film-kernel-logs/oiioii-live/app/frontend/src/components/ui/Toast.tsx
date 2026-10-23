import * as React from 'react'
import { X } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface ToastProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: 'default' | 'destructive' | 'success'
}

export type ToastActionElement = React.ReactElement

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => <>{children}</>
export const ToastViewport: React.FC<React.HTMLAttributes<HTMLDivElement>> = (props) => <div {...props} />

export const Toast = React.forwardRef<HTMLDivElement, ToastProps>(
  ({ className, variant = 'default', children, ...props }, ref) => {
    const variantStyles = {
      default: 'border-dark-200 bg-white text-dark-900 dark:border-dark-700 dark:bg-dark-900 dark:text-dark-100',
      destructive: 'destructive group border-red-500 bg-red-50 text-red-900 dark:border-red-900 dark:bg-red-950 dark:text-red-50',
      success: 'border-green-500 bg-green-50 text-green-900 dark:border-green-900 dark:bg-green-950 dark:text-green-50',
    }
    return (
      <div
        ref={ref}
        className={cn(
          'group pointer-events-auto relative flex w-full items-center justify-between space-x-4 overflow-hidden rounded-lg border p-6 pr-8 shadow-lg transition-all',
          variantStyles[variant],
          className
        )}
        {...props}
      >
        {children}
      </div>
    )
  }
)
Toast.displayName = 'Toast'

export const ToastAction: React.FC<React.ButtonHTMLAttributes<HTMLButtonElement>> = ({ className, ...props }) => (
  <button
    className={cn(
      'inline-flex h-8 shrink-0 items-center justify-center rounded-md border border-dark-200 bg-transparent px-3 text-sm font-medium transition-colors hover:bg-dark-100 focus:outline-none focus:ring-2 focus:ring-dark-400 focus:ring-offset-2',
      className
    )}
    {...props}
  />
)

export const ToastClose: React.FC<React.ButtonHTMLAttributes<HTMLButtonElement>> = ({ className, ...props }) => (
  <button
    className={cn(
      'absolute right-2 top-2 rounded-md p-1 text-dark-500 opacity-0 transition-opacity hover:text-dark-900 focus:opacity-100 focus:outline-none focus:ring-2 group-hover:opacity-100',
      className
    )}
    {...props}
  >
    <X className="h-4 w-4" />
  </button>
)

export const ToastTitle: React.FC<React.HTMLAttributes<HTMLHeadingElement>> = ({ className, ...props }) => (
  <h5 className={cn('text-sm font-semibold', className)} {...props} />
)

export const ToastDescription: React.FC<React.HTMLAttributes<HTMLParagraphElement>> = ({ className, ...props }) => (
  <div className={cn('text-sm opacity-90', className)} {...props} />
)

export { useToast, toast } from '@/hooks/useToast'