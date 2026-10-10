import React from 'react'
import ReactDOM from 'react-dom/client'
import { AssessmentGateway } from './components/AssessmentGateway'
import { LazyDispatch } from './components/LazyDispatch'
import './styles/atlas.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AssessmentGateway>
      <LazyDispatch />
    </AssessmentGateway>
  </React.StrictMode>,
)
