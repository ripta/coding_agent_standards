---
name: data-visualization
description: |
  Use this skill before making any chart, graph, or plot, in any medium or library: an HTML page, a slide, a notebook,
  a PNG for a report, or a terminal plot. It sets what a chart claims and whether a reader can trust it: titles, axis
  labels and units, zero baselines, truncated and zoomed ranges, consistent scales across related charts, direct
  labeling, minimal decoration, and data integrity. Triggers: "chart", "graph", "plot", "visualize this data",
  "y-axis", "baseline", "legend". DO NOT trigger for diagrams that plot no data, such as flowcharts or architecture
  diagrams.
---

# Data Visualization

These rules cover what a chart claims and whether a reader can trust it: titles, axes, scales, baselines, labels, and
provenance. They apply to every chart, in any medium or library.

Color, mark specs, and interaction are out of scope here. When a `dataviz` skill is available in the session, read it
too, and follow it for those. Where the two overlap, this skill wins. It overrides `dataviz` on one point in
particular: legends. See "Labels".

## Choosing to Chart

- A chart earns its place when the shape of the data is the point: a trend, a distribution, a comparison, an outlier.
  When the point is one number, state the number. When the reader needs exact values, use a table.
- Each chart makes one point. A chart that needs two takeaways is two charts.
- Use a pie or donut only for parts of one whole, with at most five slices. Otherwise use a bar chart. Readers compare
  lengths far more accurately than angles.

## No Decoration

Every mark on the chart carries data or helps a reader decode it. Anything else is a flourish, and it goes.

- Never use 3D effects, perspective, or extruded bars. They distort lengths and areas, and they hide values behind
  other values.
- No illustrations, icons, clip art, or pictograms that carry no data. No background images or textures.
- No drop shadows, gradients, glows, or bevels on marks.
- No borders around the plot area, and no boxes around the legend.
- Gridlines are faint hairlines, a shade off the background, and few. Omit them when direct labels or the axis ticks
  already make the values clear.
- Tick marks are short and light, or absent. The tick labels carry the values.
- Data points and trends sit in clear space. When the eye lands on the grid, the axes, or the frame before the data,
  they are too heavy.

## Titles and Captions

- The title states the finding, not the chart's contents. Write "p99 latency doubled after the 3.2 deploy" instead of
  "p99 latency over time".
- A subtitle or caption names what is plotted, its unit, the population, and the time range when the title does not.
- When the chart supports a specific claim in surrounding prose, the prose and the title make the same claim.
- Name the source of the data and when it was pulled. A chart of production metrics names the dashboard, query, or
  file it came from.

## Labels

Label the data directly, as close to it as possible. The eye should not bounce between a mark and a distant key.

- Name each line at its end, each bar at its base or tip, and each area inside it or beside it. Labels use text
  colors. A small color key beside the label ties it to the mark.
- Use a legend only when direct labels cannot name every series: more than four series, lines that converge at the
  labeled end, or filters that hide and show series. Place it beside the title, never below the plot or off to the
  side, and keep its order the same as the series order in the plot.
- A single series needs no legend. The title names it.
- Label values selectively: the endpoint, the extreme, or the value the title talks about. Never put a number on every
  point. The axis carries the rest.
- When direct labels collide, do not stack them. Use a short leader line, or split the chart into small multiples.
- A label that does not fit inside its mark moves outside it. It is never clipped.

## Axes

- Label every axis with the quantity and its unit: "Latency (ms)", "Requests per second", "Heap (MiB)". A unit-free
  axis is acceptable only for a true count, and the label still says what is counted.
- Omit an axis title only when the tick labels are self-describing, such as dates or category names.
- Put the unit in the axis title, not on every tick. Ticks carry numbers.
- Use round tick values at even intervals. Never let a library place ticks at 13.7, 27.4, 41.1.
- Use the units a reader thinks in. Show 1.2 s rather than 1200 ms when every value is above a second. Use binary
  prefixes (KiB, MiB) for memory and decimal prefixes (KB, MB) for network and disk throughput, and say which.
- Time axes state the time zone when the data spans hours or less. Use UTC unless the audience works in one local zone.
- Label categories horizontally. When category names are long, flip to horizontal bars instead of rotating the labels.

## Baselines and Ranges

The value axis starts at zero, and its range is the library's honest bound on the data. Any departure from that needs
an explicit reason, stated on the chart. A truncated or hand-tuned axis without one is visual deceit, whatever the
intent.

### Zero Baselines

- Bar, column, and area charts always start the value axis at zero. A bar's length is its value. A truncated axis makes
  a 5% difference look like a 5x one. No reason overrides this.
- A stacked bar or stacked area always starts at zero. Each segment's length is its value.
- When the differences that matter are too small to see from zero, do not truncate the bars. Plot the differences
  directly, as a delta from a baseline or a percent change, or switch to a dot plot or a line.

### Non-Zero Baselines

A line chart or dot plot encodes value by position, not length. Its axis may start above zero, but only for a reason
the chart states.

- Valid reasons: the quantity has no meaningful zero, such as temperature in Celsius or a timestamp. Or the variation is
  the claim, and the variation is large relative to the noise.
- Invalid reasons: the line looks flat from zero, or the library chose the range. A line that looks flat from zero may
  be flat.
- State the reason in the caption, such as "Axis starts at 40 ms to show the regression".

### Zoomed Ranges

The range bounds the data. It must not exaggerate minor fluctuations.

- When a range is zoomed into a narrow band, make it impossible to miss. Draw an axis break mark at the bottom of the
  axis. Show the lowest tick's value. Say in the caption that the axis does not start at zero.
- State the size of the change in the title or caption, in absolute and relative terms: "up 4 ms, 2%". A reader then
  judges the swing by its number, not by how much of the plot it fills.
- When a 0.3% swing fills the full plot height, the range is wrong. Widen it until the visual change matches the real
  one, or plot the change itself.

### Other Range Changes

- Do not hand-set an axis minimum or maximum, clip outliers, or pad the range to move the data, without a reason the
  chart states.
- When an outlier is clipped, mark it at the edge of the plot with its value.
- Never invert an axis unless the convention for that quantity is inverted, such as rank or depth. Say so on the axis.

### Log Scales

- Use a log scale when the data spans orders of magnitude, or when growth rates are the point.
- Label a log axis as log in its title, and use tick values at powers of ten or another clean base.
- Never use a log scale for bars. A bar's length on a log axis has no meaning, and zero cannot be plotted.

## Consistency Across Related Charts

Charts that sit together get compared, whether or not they were meant to be. Keep every encoding the same, so a
difference the reader sees is a difference in the data.

- Never put two y-scales on one plot. Use two charts that share the x-axis, or index both series to 100 at a common
  start.
- Charts placed together for comparison use the same scale, range, units, and time window.
- Small multiples share one scale across every panel. When panels must use independent scales, say so in the caption,
  because readers compare panel heights.
- An entity keeps the same color, marker, and label in every chart of a set. A filter that removes series does not
  repaint the ones left.
- Mark weights match across a set: one line width, one bar width, one marker size. A thicker line reads as more
  important.
- Keep one category order across every chart in a set. A reader who learns the order on the first chart keeps using it.
- Use one visual cue for one meaning across the set. When a dashed line means "forecast" on one chart, it means
  forecast on all of them, and nothing else is dashed.

## Data Integrity

- Plot what was measured. Do not smooth, interpolate, or resample without saying so in the caption, with the window or
  method.
- Show gaps as gaps. A line through a period with no data claims values that were never recorded. Break the line, or
  mark the gap.
- Name the aggregation. A latency chart says whether it plots the mean, the median, or p99, and over what window.
  Prefer percentiles over means for skewed data such as latency.
- When the denominator changes over time, plot a rate or a share, not a raw count. A chart of errors that ignores
  traffic growth shows growth, not errors.
- State the sample size when it is small enough to matter, and show uncertainty where the data has it, such as
  confidence intervals or min-max bands. Say what an error bar represents.
- When a comparison involves a change, such as a deploy, a config flip, or an incident, mark that point on the chart
  and label it.

## Ordering

- Sort bars by value unless the categories have a natural order, such as time, size buckets, or severity.
- Put "Other" and "Unknown" last, whatever their value.

## Before Sharing

- Read the chart cold, as someone who did not make it. Check that the title, the axes, and the caption are enough to
  understand it without the surrounding text.
- Check every axis that does not start at zero. Its reason must be on the chart.
- Check that every number in the title or the prose matches the plotted data.
- Check the rendered output at its real size, not only in the editor. Labels that collide or clip are defects.
