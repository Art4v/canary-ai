// Each shape: viewBox string + array of ellipse configs
const cloudShapes = [
  // Wide puffy cloud
  {
    viewBox: '0 0 300 120',
    ellipses: [
      { cx: 70, cy: 80, rx: 55, ry: 48 },
      { cx: 150, cy: 60, rx: 60, ry: 55 },
      { cx: 230, cy: 80, rx: 55, ry: 48 },
      { cx: 150, cy: 90, rx: 90, ry: 40 },
    ],
  },
  // Tall puffy cloud
  {
    viewBox: '0 0 200 160',
    ellipses: [
      { cx: 100, cy: 50, rx: 50, ry: 48 },
      { cx: 60, cy: 100, rx: 50, ry: 45 },
      { cx: 140, cy: 100, rx: 50, ry: 45 },
      { cx: 100, cy: 110, rx: 70, ry: 42 },
    ],
  },
  // Small round cloud
  {
    viewBox: '0 0 180 80',
    ellipses: [
      { cx: 50, cy: 50, rx: 40, ry: 35 },
      { cx: 110, cy: 40, rx: 48, ry: 40 },
      { cx: 150, cy: 55, rx: 32, ry: 28 },
    ],
  },
]

export default cloudShapes
