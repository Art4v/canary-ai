const birdShape = {
  viewBox: '0 0 40 30',
  head: { cx: 10, cy: 13, r: 5.5, fill: '#fdf586' },
  body: { cx: 22, cy: 17, rx: 11, ry: 8, fill: '#fdf586' },
  wing: {
    d: 'M17 12 Q14 0 28 8 Q24 6 20 10Z',
    fill: '#e8d44d',
  },
  beak: {
    d: 'M3 13 L9 11 L9 15Z',
    fill: '#e6a818',
  },
  eye: { cx: 9, cy: 11, r: 1.5, fill: '#333' },
  tail: {
    d: 'M33 15 L40 10 L38 17 L40 24 L33 19Z',
    fill: '#fdf586',
  },
}

export default birdShape
