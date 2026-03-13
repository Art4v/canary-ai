import StarField from './StarField.jsx'
import CloudLayer from './CloudLayer.jsx'
import './SkyBackground.css'

export default function SkyBackground() {
  return (
    <div className="sky-background">
      <StarField />
      <CloudLayer />
    </div>
  )
}
