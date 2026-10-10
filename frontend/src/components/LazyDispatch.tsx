import { lazy, Suspense } from 'react'

const DispatchCanvas = lazy(() => import('../App'))

export function LazyDispatch() {
  return (
    <Suspense
      fallback={
        <main className="assessment-gateway" role="status">
          Opening Dispatch Canvas…
        </main>
      }
    >
      <DispatchCanvas />
    </Suspense>
  )
}
