# Bayesian Hierarchical Growth Modeling For Organoids

Date: 2026-04-24

## Motivation

For organoid growth experiments, a Bayesian hierarchical growth model can be clearer than ordinary line charts when the data include:

- many organoids, wells, or fields per day
- unequal replicate counts across dates
- noisy measurements
- missing days
- small but consistent growth differences
- repeated measurements from the same organoid

The key idea is to estimate the full growth trajectory rather than only plotting daily `mean ± error bar`. The most useful paper figure is often the posterior difference between a treatment and the control.

## Recommended Main Model

For growth metrics such as area:

```text
log(area) ~ group * day + hierarchical variation
```

For a simpler growth-rate model:

```text
log(area) = initial_size + growth_rate_group * day + error
```

If the same organoids are tracked over time, use a repeated-measurement model:

```text
log(area_i,t) = alpha_i + beta_group * day_t + error
```

If different organoids or fields are sampled each date, use a group-date or image-level hierarchical model:

```text
measurement ~ group + date + group:date + replicate variation
```

For the current DEO/App80 derived metric table, the observations are image-level summaries rather than one-to-one tracked organoids, so the initial practical test should use an image-level hierarchical log-growth model.

## Better Growth-Curve Presentation

Instead of plotting only:

```text
Day 0, Day 1, Day 2, ...
mean ± SD or SEM
```

Use:

```text
solid line = posterior median trajectory
shaded band = 95% credible interval
points = raw observations
optional thin lines = posterior samples
```

This makes the estimated growth trajectory smoother and easier to interpret.

## Most Useful Plot: Difference From Control

For each day, plot the posterior difference from control:

```text
Delta(t) = treatment(t) - control(t)
```

For growth, a fold-scale version is usually better:

```text
Delta log2(t) = log2(treatment / control)
```

Interpretation:

```text
0 means no difference
above 0 means larger than control
below 0 means smaller than control
shaded band means uncertainty
```

This directly shows when the treatment separates from control.

## Probability Plot

Bayesian analysis also supports direct probability statements:

```text
P(treatment > control)
P(treatment < control)
P(treatment growth rate > control growth rate)
P(treatment growth rate < control growth rate)
```

For inhibitory drug response, plot:

```text
P(treatment < control)
```

Useful horizontal reference lines:

```text
0.5 = no directional preference
0.95 = strong posterior support
```

## Growth-Rate Posterior Plot

Rather than comparing size at each day, estimate the growth-rate posterior for each group.

Plot:

```text
posterior distribution of beta_control
posterior distribution of beta_treatment
posterior distribution of beta_treatment - beta_control
```

This answers whether the treatment changes growth speed, not only whether organoids differ on one day.

## Raincloud And Distribution Support

A useful companion layout is:

```text
top: posterior fitted growth curves
bottom: raincloud or violin distributions at selected days
```

Suggested selected days:

```text
D0, D3, D7, D10
```

This helps show the raw distribution behind the fitted trend.

## Small Multiples

If many treatments are present, avoid putting all curves in one crowded plot.

Use one panel per treatment:

```text
control posterior curve
treatment posterior curve
difference-from-control curve
```

This is usually clearer than many colored lines in one panel.

## Suggested Paper Layout

Recommended figure structure:

```text
Figure X. Bayesian analysis of organoid growth dynamics.

A. Representative brightfield images across days.
B. Raw normalized organoid trajectories.
C. Bayesian posterior growth curves, median with 95% credible interval.
D. Posterior difference from control, log2(treatment/control).
E. Posterior growth-rate difference.
F. Probability of growth inhibition over time.
```

The strongest panels are usually:

- `D`: posterior log2 treatment/control over time
- `E`: posterior growth-rate difference
- `F`: probability of growth inhibition or acceleration

## Non-Bayesian Alternative

If a Bayesian model is too hard to explain for the target audience, a clean alternative is model-based estimated marginal means.

Fit:

```text
growth ~ group * day
```

Then plot predicted means with confidence intervals. This looks similar to posterior growth curves but is easier for some reviewers.

## Recommendation For The Current DEO Figures

Use the ordinary growth curve as a familiar entry point, then add model-based plots to make differences clear:

```text
Main figure:
B. raw trajectories + mean
C. Bayesian fitted growth curve
D. posterior difference from control

Supplement:
growth-rate posterior
posterior probability table
raw area distribution per selected day
```

The most direct plot is:

```text
log2(treatment / control) over time with 95% credible interval
```

It shows the biological effect without forcing the reader to compare noisy growth curves by eye.
