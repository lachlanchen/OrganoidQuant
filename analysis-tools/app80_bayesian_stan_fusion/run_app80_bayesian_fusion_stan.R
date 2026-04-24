#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(cmdstanr)
  library(dplyr)
  library(ggplot2)
  library(jsonlite)
  library(posterior)
  library(readr)
  library(scales)
  library(stringr)
  library(tibble)
  library(tidyr)
})

repo_root <- normalizePath(getwd(), mustWork = TRUE)

default_input <- file.path(
  repo_root,
  "analysis-output",
  "app80_all_concentrations_multiscale_large_recovery",
  "profiling",
  "quantification",
  "per_image_metrics.csv"
)

default_output <- file.path(
  repo_root,
  "analysis-output",
  "app80_all_concentrations_multiscale_large_recovery",
  "bayesian_stan_fusion_v1"
)

default_stan <- file.path(
  repo_root,
  "analysis-tools",
  "app80_bayesian_stan_fusion",
  "app80_log_fusion_metric.stan"
)

parse_args <- function(args) {
  parsed <- list(
    input = default_input,
    output = default_output,
    stan = default_stan,
    metric = "normalized_edge_over_count_curvature",
    metric_label = "Normalized edge / (count * curvature)",
    draws = 1000,
    warmup = 1000,
    chains = 4,
    seed = 20260424
  )

  i <- 1
  while (i <= length(args)) {
    key <- args[[i]]
    if (!startsWith(key, "--")) {
      stop("Unexpected argument: ", key)
    }
    if (i == length(args)) {
      stop("Missing value for argument: ", key)
    }
    value <- args[[i + 1]]
    key <- sub("^--", "", key)
    if (!key %in% names(parsed)) {
      stop("Unknown argument: --", key)
    }
    if (key %in% c("draws", "warmup", "chains", "seed")) {
      parsed[[key]] <- as.integer(value)
    } else {
      parsed[[key]] <- value
    }
    i <- i + 2
  }

  parsed
}

args <- parse_args(commandArgs(trailingOnly = TRUE))

dir.create(args$output, recursive = TRUE, showWarnings = FALSE)
for (subdir in c("data", "diagnostics", "figures", "stan", "tables")) {
  dir.create(file.path(args$output, subdir), recursive = TRUE, showWarnings = FALSE)
}

input_path <- normalizePath(args$input, mustWork = TRUE)
stan_path <- normalizePath(args$stan, mustWork = TRUE)
output_dir <- normalizePath(args$output, mustWork = TRUE)

raw <- read_csv(input_path, show_col_types = FALSE)
required_cols <- c("concentration", "relative_day", args$metric)
missing_cols <- setdiff(required_cols, names(raw))
if (length(missing_cols) > 0) {
  stop("Input is missing required columns: ", paste(missing_cols, collapse = ", "))
}

prepared <- raw %>%
  mutate(
    concentration = as.character(concentration),
    relative_day = as.numeric(relative_day),
    fusion_metric = as.numeric(.data[[args$metric]])
  )

excluded <- prepared %>%
  filter(
    is.na(concentration) |
      is.na(relative_day) |
      is.na(fusion_metric) |
      fusion_metric <= 0
  )

data <- prepared %>%
  filter(
    !is.na(concentration),
    !is.na(relative_day),
    !is.na(fusion_metric),
    fusion_metric > 0
  )

preferred_groups <- c("No", "10uM", "20uM", "50uM", "100uM")
observed_groups <- unique(data$concentration)
groups <- preferred_groups[preferred_groups %in% observed_groups]
groups <- c(groups, sort(setdiff(observed_groups, groups)))
if (!"No" %in% groups) {
  stop("Control group 'No' was not found in concentration column.")
}

group_labels <- c(
  "No" = "0 umol",
  "10uM" = "10 umol",
  "20uM" = "20 umol",
  "50uM" = "50 umol",
  "100uM" = "100 umol"
)

data <- data %>%
  mutate(
    concentration = factor(concentration, levels = groups),
    group_id = as.integer(concentration),
    log_fusion_metric = log(fusion_metric)
  )

day_mean <- mean(data$relative_day)
day_sd <- sd(data$relative_day)
if (!is.finite(day_sd) || day_sd <= 0) {
  stop("relative_day has zero or invalid variance.")
}

data <- data %>%
  mutate(day_scaled = (relative_day - day_mean) / day_sd)

write_csv(data, file.path(output_dir, "data", "app80_fusion_model_input.csv"))
write_csv(excluded, file.path(output_dir, "data", "excluded_rows.csv"))

replicate_counts <- data %>%
  count(concentration, relative_day, name = "n_images") %>%
  arrange(concentration, relative_day)
write_csv(replicate_counts, file.path(output_dir, "tables", "image_counts_by_group_day.csv"))

output_stan_path <- file.path(output_dir, "stan", basename(stan_path))
file.copy(stan_path, output_stan_path, overwrite = TRUE)

stan_data <- list(
  N = nrow(data),
  G = length(groups),
  group_id = data$group_id,
  day_scaled = data$day_scaled,
  y = data$log_fusion_metric,
  day_sd = day_sd
)

message("Compiling Stan model: ", output_stan_path)
model <- cmdstan_model(output_stan_path)

csv_dir <- file.path(output_dir, "diagnostics", "cmdstan_csv")
dir.create(csv_dir, recursive = TRUE, showWarnings = FALSE)

message("Sampling App80 Bayesian fusion model...")
fit <- model$sample(
  data = stan_data,
  seed = args$seed,
  chains = args$chains,
  parallel_chains = min(args$chains, parallel::detectCores(logical = FALSE)),
  iter_warmup = args$warmup,
  iter_sampling = args$draws,
  refresh = 200,
  output_dir = csv_dir
)

saveRDS(fit, file.path(output_dir, "diagnostics", "cmdstanr_fit.rds"))
writeLines(capture.output(fit$cmdstan_diagnose()), file.path(output_dir, "diagnostics", "cmdstan_diagnose.txt"))

fit_summary <- fit$summary()
write_csv(fit_summary, file.path(output_dir, "diagnostics", "stan_parameter_summary.csv"))

draws_matrix <- as_draws_matrix(fit$draws(c("alpha", "beta_scaled", "beta_per_day", "sigma")))
n_draws <- nrow(draws_matrix)
alpha_mat <- sapply(seq_along(groups), function(g) draws_matrix[, paste0("alpha[", g, "]")])
beta_scaled_mat <- sapply(seq_along(groups), function(g) draws_matrix[, paste0("beta_scaled[", g, "]")])
beta_per_day_mat <- sapply(seq_along(groups), function(g) draws_matrix[, paste0("beta_per_day[", g, "]")])
colnames(alpha_mat) <- groups
colnames(beta_scaled_mat) <- groups
colnames(beta_per_day_mat) <- groups

summarize_draws <- function(x) {
  tibble(
    median = as.numeric(quantile(x, 0.50, names = FALSE)),
    lower_95 = as.numeric(quantile(x, 0.025, names = FALSE)),
    upper_95 = as.numeric(quantile(x, 0.975, names = FALSE))
  )
}

day_grid <- seq(min(data$relative_day), max(data$relative_day), length.out = 121)
focus_day <- if (6 %in% data$relative_day) 6 else max(data$relative_day)
control_idx <- which(groups == "No")
treatment_groups <- setdiff(groups, "No")

fusion_summary <- bind_rows(lapply(seq_along(groups), function(g) {
  bind_rows(lapply(day_grid, function(day) {
    day_scaled <- (day - day_mean) / day_sd
    log_mu <- alpha_mat[, g] + beta_scaled_mat[, g] * day_scaled
    summarize_draws(exp(log_mu)) %>%
      mutate(
        concentration = groups[[g]],
        relative_day = day,
        log_median = as.numeric(quantile(log_mu, 0.50, names = FALSE)),
        log_lower_95 = as.numeric(quantile(log_mu, 0.025, names = FALSE)),
        log_upper_95 = as.numeric(quantile(log_mu, 0.975, names = FALSE))
      )
  }))
})) %>%
  relocate(concentration, relative_day)

difference_summary <- bind_rows(lapply(setdiff(seq_along(groups), control_idx), function(g) {
  bind_rows(lapply(day_grid, function(day) {
    day_scaled <- (day - day_mean) / day_sd
    log_control <- alpha_mat[, control_idx] + beta_scaled_mat[, control_idx] * day_scaled
    log_treatment <- alpha_mat[, g] + beta_scaled_mat[, g] * day_scaled
    log2_difference <- (log_treatment - log_control) / log(2)

    summarize_draws(log2_difference) %>%
      mutate(
        concentration = groups[[g]],
        relative_day = day,
        probability_higher_than_control = mean(log2_difference > 0),
        probability_lower_than_control = mean(log2_difference < 0)
      )
  }))
})) %>%
  relocate(concentration, relative_day)

focus_day_draws <- bind_rows(lapply(setdiff(seq_along(groups), control_idx), function(g) {
  day_scaled <- (focus_day - day_mean) / day_sd
  log_control <- alpha_mat[, control_idx] + beta_scaled_mat[, control_idx] * day_scaled
  log_treatment <- alpha_mat[, g] + beta_scaled_mat[, g] * day_scaled
  tibble(
    concentration = groups[[g]],
    focus_day = focus_day,
    log2_difference_vs_control = (log_treatment - log_control) / log(2)
  )
})) %>%
  mutate(concentration = factor(concentration, levels = treatment_groups))

focus_day_summary <- focus_day_draws %>%
  group_by(concentration, focus_day) %>%
  summarise(
    median = median(log2_difference_vs_control),
    lower_95 = quantile(log2_difference_vs_control, 0.025),
    upper_95 = quantile(log2_difference_vs_control, 0.975),
    probability_higher_than_control = mean(log2_difference_vs_control > 0),
    probability_lower_than_control = mean(log2_difference_vs_control < 0),
    .groups = "drop"
  ) %>%
  arrange(concentration)

fusion_rate_summary <- bind_rows(lapply(seq_along(groups), function(g) {
  summarize_draws(beta_per_day_mat[, g]) %>%
    mutate(
      concentration = groups[[g]],
      probability_positive_slope = mean(beta_per_day_mat[, g] > 0),
      probability_negative_slope = mean(beta_per_day_mat[, g] < 0)
    )
})) %>%
  relocate(concentration)

fusion_rate_diff_summary <- bind_rows(lapply(setdiff(seq_along(groups), control_idx), function(g) {
  diff <- beta_per_day_mat[, g] - beta_per_day_mat[, control_idx]
  summarize_draws(diff) %>%
    mutate(
      concentration = groups[[g]],
      probability_faster_increase_than_control = mean(diff > 0),
      probability_slower_increase_than_control = mean(diff < 0)
    )
})) %>%
  relocate(concentration)

write_csv(fusion_summary, file.path(output_dir, "tables", "posterior_fusion_curve_summary.csv"))
write_csv(difference_summary, file.path(output_dir, "tables", "posterior_log2_difference_from_control_by_day.csv"))
write_csv(focus_day_summary, file.path(output_dir, "tables", paste0("posterior_day", focus_day, "_log2_difference_vs_control.csv")))
write_csv(focus_day_draws, file.path(output_dir, "tables", paste0("posterior_day", focus_day, "_log2_difference_draws.csv")))
write_csv(fusion_rate_summary, file.path(output_dir, "tables", "posterior_fusion_slope_by_group.csv"))
write_csv(fusion_rate_diff_summary, file.path(output_dir, "tables", "posterior_fusion_slope_difference_vs_control.csv"))

group_colors <- c(
  "No" = "#1F2937",
  "10uM" = "#2563EB",
  "20uM" = "#059669",
  "50uM" = "#D97706",
  "100uM" = "#DC2626"
)
group_colors <- group_colors[groups]
legend_labels <- group_labels[groups]
legend_labels[is.na(legend_labels)] <- groups[is.na(legend_labels)]

save_plot <- function(plot, stem, width = 7.2, height = 4.8) {
  png_path <- file.path(output_dir, "figures", paste0(stem, ".png"))
  pdf_path <- file.path(output_dir, "figures", paste0(stem, ".pdf"))
  ggsave(png_path, plot, width = width, height = height, dpi = 300, bg = "white")
  ggsave(pdf_path, plot, width = width, height = height, bg = "white")
}

base_theme <- theme_classic(base_size = 12) +
  theme(
    legend.title = element_blank(),
    legend.position = "top",
    axis.text.x = element_text(color = "black"),
    axis.text.y = element_text(color = "black"),
    plot.title = element_text(face = "bold", size = 13),
    strip.background = element_blank(),
    strip.text = element_text(face = "bold")
  )

scale_color_groups <- scale_color_manual(values = group_colors, breaks = groups, labels = legend_labels)
scale_fill_groups <- scale_fill_manual(values = group_colors, breaks = groups, labels = legend_labels)
treatment_colors <- group_colors[treatment_groups]
treatment_labels <- legend_labels[treatment_groups]

fusion_plot_base <- ggplot() +
  geom_point(
    data = data,
    aes(x = relative_day, y = fusion_metric, color = concentration),
    alpha = 0.32,
    size = 1.0,
    position = position_jitter(width = 0.055, height = 0)
  ) +
  geom_ribbon(
    data = fusion_summary,
    aes(x = relative_day, ymin = lower_95, ymax = upper_95, fill = concentration),
    alpha = 0.16,
    linewidth = 0
  ) +
  geom_line(
    data = fusion_summary,
    aes(x = relative_day, y = median, color = concentration),
    linewidth = 1.05
  ) +
  scale_color_groups +
  scale_fill_groups +
  scale_x_continuous(breaks = sort(unique(data$relative_day))) +
  guides(fill = "none") +
  base_theme

fusion_plot <- fusion_plot_base +
  scale_y_continuous(labels = label_number()) +
  labs(
    title = "App80 posterior fusion trajectories",
    x = "Relative day",
    y = args$metric_label
  )
save_plot(fusion_plot, "app80_bayesian_posterior_fusion_curves")

fusion_log_plot <- fusion_plot_base +
  scale_y_log10(labels = label_number()) +
  labs(
    title = "App80 posterior fusion trajectories, log scale",
    x = "Relative day",
    y = paste0(args$metric_label, " (log scale)")
  )
save_plot(fusion_log_plot, "app80_bayesian_posterior_fusion_curves_log_y")

fusion_lines_only <- ggplot(fusion_summary, aes(x = relative_day, color = concentration, fill = concentration)) +
  geom_ribbon(aes(ymin = lower_95, ymax = upper_95), alpha = 0.18, linewidth = 0) +
  geom_line(aes(y = median), linewidth = 1.25) +
  scale_color_groups +
  scale_fill_groups +
  scale_y_continuous(labels = label_number()) +
  scale_x_continuous(breaks = sort(unique(data$relative_day))) +
  labs(
    title = "App80 posterior fusion trajectories, model only",
    x = "Relative day",
    y = args$metric_label
  ) +
  guides(fill = "none") +
  base_theme
save_plot(fusion_lines_only, "app80_bayesian_posterior_fusion_curves_lines_only")

difference_plot <- ggplot(difference_summary, aes(x = relative_day, color = concentration, fill = concentration)) +
  geom_hline(yintercept = 0, linetype = "dashed", linewidth = 0.45, color = "grey35") +
  geom_ribbon(aes(ymin = lower_95, ymax = upper_95), alpha = 0.16, linewidth = 0) +
  geom_line(aes(y = median), linewidth = 1.05) +
  scale_color_manual(values = treatment_colors, breaks = treatment_groups, labels = treatment_labels) +
  scale_fill_manual(values = treatment_colors, breaks = treatment_groups, labels = treatment_labels) +
  scale_x_continuous(breaks = sort(unique(data$relative_day))) +
  labs(
    title = "App80 posterior fusion difference from 0 umol",
    x = "Relative day",
    y = "log2(concentration / 0 umol)"
  ) +
  guides(fill = "none") +
  base_theme
save_plot(difference_plot, "app80_bayesian_log2_difference_from_control")

probability_plot <- ggplot(difference_summary, aes(x = relative_day, y = probability_higher_than_control, color = concentration)) +
  geom_hline(yintercept = 0.5, linetype = "dashed", linewidth = 0.45, color = "grey55") +
  geom_hline(yintercept = 0.95, linetype = "dotted", linewidth = 0.45, color = "grey35") +
  geom_line(linewidth = 1.05) +
  scale_color_manual(values = treatment_colors, breaks = treatment_groups, labels = treatment_labels) +
  scale_y_continuous(limits = c(0, 1), breaks = seq(0, 1, 0.25)) +
  scale_x_continuous(breaks = sort(unique(data$relative_day))) +
  labs(
    title = "App80 probability of higher fusion proxy than 0 umol",
    x = "Relative day",
    y = "P(concentration > 0 umol)"
  ) +
  base_theme
save_plot(probability_plot, "app80_bayesian_probability_higher_than_control")

focus_density_plot <- ggplot(focus_day_draws, aes(x = log2_difference_vs_control, color = concentration, fill = concentration)) +
  geom_vline(xintercept = 0, linetype = "dashed", linewidth = 0.45, color = "grey35") +
  geom_density(alpha = 0.18, linewidth = 0.9) +
  scale_color_manual(values = treatment_colors, breaks = treatment_groups, labels = treatment_labels) +
  scale_fill_manual(values = treatment_colors, breaks = treatment_groups, labels = treatment_labels) +
  labs(
    title = paste0("App80 day ", focus_day, " fusion difference from 0 umol"),
    x = "log2(concentration / 0 umol)",
    y = "Posterior density"
  ) +
  guides(fill = "none") +
  base_theme
save_plot(focus_density_plot, paste0("app80_bayesian_day", focus_day, "_fusion_difference_posteriors"))

focus_interval_plot <- ggplot(focus_day_summary, aes(x = concentration, y = median, color = concentration)) +
  geom_hline(yintercept = 0, linetype = "dashed", linewidth = 0.45, color = "grey35") +
  geom_pointrange(aes(ymin = lower_95, ymax = upper_95), linewidth = 0.7, size = 0.55) +
  scale_x_discrete(limits = treatment_groups, labels = treatment_labels) +
  scale_color_manual(values = treatment_colors, breaks = treatment_groups, labels = treatment_labels) +
  labs(
    title = paste0("App80 day ", focus_day, " fusion difference summary"),
    x = NULL,
    y = "log2 difference vs 0 umol"
  ) +
  base_theme +
  theme(legend.position = "none")
save_plot(focus_interval_plot, paste0("app80_bayesian_day", focus_day, "_fusion_difference_intervals"), width = 6.0, height = 4.4)

diagnostic_summary <- fit_summary %>%
  summarise(
    max_rhat = suppressWarnings(max(rhat, na.rm = TRUE)),
    min_ess_bulk = suppressWarnings(min(ess_bulk, na.rm = TRUE)),
    min_ess_tail = suppressWarnings(min(ess_tail, na.rm = TRUE))
  )
write_csv(diagnostic_summary, file.path(output_dir, "diagnostics", "stan_diagnostic_summary.csv"))

manifest <- list(
  created_at = format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z"),
  input_metrics = input_path,
  output_dir = output_dir,
  stan_file_source = stan_path,
  stan_file = output_stan_path,
  environment = list(
    conda_env = "deo-r-stan",
    r_version = R.version.string,
    cmdstanr_version = as.character(packageVersion("cmdstanr")),
    cmdstan_path = cmdstan_path(),
    cmdstan_version = as.character(cmdstan_version())
  ),
  model = list(
    response = paste0("log(", args$metric, ")"),
    metric_label = args$metric_label,
    formula = "log(fusion_metric) ~ concentration-specific intercept + concentration-specific slope * relative_day",
    control_group = "No",
    legend_order = unname(legend_labels),
    focus_day = focus_day,
    note = "Each microscopy image is one observation. Higher default metric values are interpreted as stronger fusion proxy signal."
  ),
  data = list(
    n_raw_rows = nrow(raw),
    n_used_rows = nrow(data),
    n_excluded_rows = nrow(excluded),
    groups = groups,
    day_mean = day_mean,
    day_sd = day_sd,
    relative_day_min = min(data$relative_day),
    relative_day_max = max(data$relative_day)
  ),
  sampling = list(
    chains = args$chains,
    warmup = args$warmup,
    draws_per_chain = args$draws,
    posterior_draws_total = n_draws,
    seed = args$seed
  )
)

write_json(manifest, file.path(output_dir, "run_manifest.json"), pretty = TRUE, auto_unbox = TRUE)

readme <- c(
  "# App80 Bayesian Stan Fusion Analysis",
  "",
  "This folder contains a Stan-based Bayesian analysis of App80 fusion proxy trajectories.",
  "",
  "Default response:",
  "",
  "```text",
  "log(normalized_edge_over_count_curvature)",
  "```",
  "",
  "Model:",
  "",
  "```text",
  "log(fusion_metric) ~ concentration-specific intercept + concentration-specific slope * relative_day",
  "```",
  "",
  "Control group: `No`, displayed as `0 umol`.",
  "",
  "Legend order is fixed from small to large: `0 umol`, `10 umol`, `20 umol`, `50 umol`, `100 umol`.",
  "",
  paste0("Focus day for endpoint comparison: `Day ", focus_day, "`."),
  "",
  "Key outputs:",
  "",
  "- `figures/app80_bayesian_posterior_fusion_curves.png`",
  "- `figures/app80_bayesian_posterior_fusion_curves_log_y.png`",
  "- `figures/app80_bayesian_posterior_fusion_curves_lines_only.png`",
  "- `figures/app80_bayesian_log2_difference_from_control.png`",
  "- `figures/app80_bayesian_probability_higher_than_control.png`",
  paste0("- `figures/app80_bayesian_day", focus_day, "_fusion_difference_posteriors.png`"),
  paste0("- `figures/app80_bayesian_day", focus_day, "_fusion_difference_intervals.png`"),
  "- `tables/posterior_fusion_curve_summary.csv`",
  "- `tables/posterior_log2_difference_from_control_by_day.csv`",
  paste0("- `tables/posterior_day", focus_day, "_log2_difference_vs_control.csv`"),
  "- `tables/posterior_fusion_slope_by_group.csv`"
)
writeLines(readme, file.path(output_dir, "README.md"))

message("Completed App80 Bayesian Stan fusion analysis: ", output_dir)
