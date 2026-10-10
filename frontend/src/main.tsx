import React from 'react'
import ReactDOM from 'react-dom/client'
import { LazyDispatch } from './components/LazyDispatch'
import './styles/atlas.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <LazyDispatch />
  </React.StrictMode>,
)
