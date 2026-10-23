/* Browser subset of D3 7.9.0. Build with:
   npm install --no-save d3@7.9.0 esbuild@0.25.12
   esbuild d3-lite-entry.js --bundle --minify --format=iife --target=es2020 --outfile=d3-lite.js
   The transition import also installs selection.transition(). */
import {
  axisBottom, axisLeft, extent, format, interpolateLab, line, max, min,
  minIndex, pointer, range, scaleBand, scaleLinear, scaleLog,
  scaleSequential, select, transition
} from 'd3';

window.d3 = {
  axisBottom, axisLeft, extent, format, interpolateLab, line, max, min,
  minIndex, pointer, range, scaleBand, scaleLinear, scaleLog,
  scaleSequential, select, transition
};
