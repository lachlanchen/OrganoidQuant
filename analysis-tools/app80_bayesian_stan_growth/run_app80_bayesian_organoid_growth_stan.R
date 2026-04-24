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

default_organoid_input <- file.path(
  repo_root,
  "analysis-output",
  "app80_all_concentrations_multiscale_large_recovery",
  "bayesian_stan_organoid_level_growth_v1",
  "data",
  "app80_organoid_level_growth_model_input.csv"
)

default_output <- file.path(
  repo_root,
  "analysis-output",
  "app80_all_concentrations_multiscale_large_recovery",
  "bayesian_stan_organoid_level_growth_v1"
)

default_stan <- file.path(
  repo_root,
  "analysis-tools",
  "app80_bayesian_stan_growth",
  "app80_log_organoid_area_growth.stan"
)

parse_args <- function(args) {
  parsed <- list(
    input = default_organoid_input,
    output = default_output,
    stan = default_stan,
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
required_cols <- c("organoid_uid", "image_uid", "concentration", "relative_day", "area_px")
missing_cols <- setdiff(required_cols, names(raw))
if (length(missing_cols) > 0) {
  stop("Input is missing required columns: ", paste(missing_cols, collapse = ", "))
}

data <- raw %>%
  mutate(
    organoid_uid = as.character(organoid_uid),
    image_uid = as.character(image_uid),
    concentration = as.character(concentration),
    relative_day = as.numeric(relative_day),
    area_px = as.numeric(area_px)
  ) %>%
  filter(
    !is.na(organoid_uid),
    !is.na(image_uid),
    !is.na(concentration),
    !is.na(relative_day),
    !is.na(area_px),
    area_px > 0
  )

preferred_groups <- c("No", "10uM", "20uM", "50uM", "100uM")
observed_groups <- unique(data$concentration)
groups <- preferred_groups[preferred_groups %in% observed_groups]
groups <- c(groups, sort(setdiff(observed_groups, groups)))
if (!"No" %in% groups) {
  stop("Control group 'No' was not found in concentration column.")
}

image_levels <- sort(unique(data$image_uid))
data <- data %>%
  mutate(
    concentration = factor(concentration, levels = groups),
    group_id = as.integer(concentration),
    image_id = match(image_uid, image_levels),
    log_area = log(area_px)
  )

day_mean <- mean(data$relative_day)
day_sd <- sd(data$relative_day)
if (!is.finite(day_sd) || day_sd <= 0) {
  stop("relative_day has zero or invalid variance.")
}

data <- data %>%
  mutate(day_scaled = (relative_day - day_mean) / day_sd)

write_csv(data, file.path(output_dir, "data", "app80_organoid_level_growth_model_input_prepared.csv"))

organoid_counts <- data %>%
  count(concentration, relative_day, name = "n_organoids") %>%
  arrange(concentration, relative_day)
write_csv(organoid_counts, file.path(output_dir, "tables", "organoid_counts_by_group_day.csv"))

image_counts <- data %>%
  distinct(concentration, relative_day, image_uid) %>%
  count(concentration, relative_day, name = "n_images") %>%
  arrange(concentration, relative_day)
write_csv(image_counts, file.path(output_dir, "tables", "image_counts_by_group_day.csv"))

output_stan_path <- file.path(output_dir, "stan", basename(stan_path))
file.copy(stan_path, output_stan_path, overwrite = TRUE)

stan_data <- list(
  N = nrow(data),
  G = length(groups),
  I = length(image_levels),
  group_id = data$group_id,
  image_id = data$image_id,
  day_scaled = data$day_scaled,
  y = data$log_area,
  day_sd = day_sd
)

message("Compiling Stan model: ", output_stan_path)
model <- cmdstan_model(output_stan_path)

csv_dir <- file.path(output_dir, "diagnostics", "cmdstan_csv")
dir.create(csv_dir, recursive = TRUE, showWarnings = FALSE)

message("Sampling App80 organoid-level Bayesian growth model...")
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

draws_matrix <- as_draws_matrix(fit$draws(c("alpha", "beta_scaled", "beta_per_day", "sigma", "sigma_image")))
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
control_idx <- which(groups == "No")

growth_summary <- bind_rows(lapply(seq_along(groups), function(g) {
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
        probability_larger_than_control = mean(log2_difference > 0),
        probability_smaller_than_control = mean(log2_difference < 0)
      )
  }))
})) %>%
  relocate(concentration, relative_day)

growth_rate_summary <- bind_rows(lapply(seq_along(groups), function(g) {
  summarize_draws(beta_per_day_mat[, g]) %>%
    mutate(
      concentration = groups[[g]],
      probability_positive_growth_rate = mean(beta_per_day_mat[, g] > 0),
      probability_negative_growth_rate = mean(beta_per_day_mat[, g] < 0)
    )
})) %>%
  relocate(concentration)

growth_rate_diff_summary <- bind_rows(lapply(setdiff(seq_along(groups), control_idx), function(g) {
  diff <- beta_per_day_mat[, g] - beta_per_day_mat[, control_idx]
  summarize_draws(diff) %>%
    mutate(
      concentration = groups[[g]],
      probability_faster_than_control = mean(diff > 0),
      probability_slower_than_control = mean(diff < 0)
    )
})) %>%
  relocate(concentration)

growth_rate_diff_draws <- bind_rows(lapply(setdiff(seq_along(groups), control_idx), function(g) {
  tibble(
    concentration = groups[[g]],
    growth_rate_difference_vs_control = beta_per_day_mat[, g] - beta_per_day_mat[, control_idx]
  )
}))

write_csv(growth_summary, file.path(output_dir, "tables", "posterior_growth_curve_summary.csv"))
write_csv(difference_summary, file.path(output_dir, "tables", "posterior_log2_difference_from_control_by_day.csv"))
write_csv(growth_rate_summary, file.path(output_dir, "tables", "posterior_growth_rate_by_group.csv"))
write_csv(growth_rate_diff_summary, file.path(output_dir, "tables", "posterior_growth_rate_difference_vs_control.csv"))
write_csv(growth_rate_diff_draws, file.path(output_dir, "tables", "posterior_growth_rate_difference_draws.csv"))

group_colors <- c(
  "No" = "#1F2937",
  "10uM" = "#2563EB",
  "20uM" = "#059669",
  "50uM" = "#D97706",
  "100uM" = "#DC2626"
)
group_colors <- group_colors[groups]

save_plot <- function(plot, stem, width = 7.2, height = 4.8) {
  png_path <- file.path(output_dir, "figures", paste0(stem, ".png"))
  pdf_path <- file.path(output_dir, "figures", paste0(stem, ".pdf"))
  ggsave(png_path, plot, width = width, height = height, dpi = 300, bg = "white")
  ggsave(pdf_path, plot, width = width, height = height, bg = "white")
}

base_theme <- theme_classic(base_size = 12) +
  theme(
    legend.title = element_blank(),
    axis.text.x = element_text(color = "black"),
    axis.text.y = element_text(color = "black"),
    plot.title = element_text(face = "bold", size = 13),
    strip.background = element_blank(),
    strip.text = element_text(face = "bold")
  )

growth_plot_base <- ggplot() +
  geom_point(
    data = data,
    aes(x = relative_day, y = area_px, color = concentration),
    alpha = 0.055,
    size = 0.65,
    position = position_jitter(width = 0.055, height = 0)
  ) +
  geom_ribbon(
    data = growth_summary,
    aes(x = relative_day, ymin = lower_95, ymax = upper_95, fill = concentration),
    alpha = 0.16,
    linewidth = 0
  ) +
  geom_line(
    data = growth_summary,
    aes(x = relative_day, y = median, color = concentration),
    linewidth = 1.05
  ) +
  scale_color_manual(values = group_colors) +
  scale_fill_manual(values = group_colors) +
  scale_x_continuous(breaks = sort(unique(data$relative_day))) +
  guides(fill = "none") +
  base_theme

growth_plot <- growth_plot_base +
  scale_y_continuous(labels = comma) +
  labs(
    title = "App80 organoid-level posterior growth curves",
    x = "Relative day",
    y = "Single-organoid area (px)"
  )

save_plot(growth_plot, "app80_organoid_level_bayesian_posterior_growth_curves")

growth_log_plot <- growth_plot_base +
  scale_y_log10(labels = comma) +
  labs(
    title = "App80 organoid-level posterior growth curves, log scale",
    x = "Relative day",
    y = "Single-organoid area (px, log scale)"
  )

save_plot(growth_log_plot, "app80_organoid_level_bayesian_posterior_growth_curves_log_y")

growth_lines_only <- ggplot(growth_summary, aes(x = relative_day, color = concentration, fill = concentration)) +
  geom_ribbon(aes(ymin = lower_95, ymax = upper_95), alpha = 0.18, linewidth = 0) +
  geom_line(aes(y = median), linewidth = 1.25) +
  scale_color_manual(values = group_colors) +
  scale_fill_manual(values = group_colors) +
  scale_y_continuous(labels = comma) +
  scale_x_continuous(breaks = sort(unique(data$relative_day))) +
  labs(
    title = "App80 organoid-level posterior growth curves, model only",
    x = "Relative day",
    y = "Single-organoid area (px)"
  ) +
  guides(fill = "none") +
  base_theme

save_plot(growth_lines_only, "app80_organoid_level_bayesian_posterior_growth_curves_lines_only")

growth_lines_only_log <- growth_lines_only +
  scale_y_log10(labels = comma) +
  labs(
    title = "App80 organoid-level posterior growth curves, model only, log scale",
    x = "Relative day",
    y = "Single-organoid area (px, log scale)"
  )

save_plot(growth_lines_only_log, "app80_organoid_level_bayesian_posterior_growth_curves_lines_only_log_y")

difference_plot <- ggplot(difference_summary, aes(x = relative_day, color = concentration, fill = concentration)) +
  geom_hline(yintercept = 0, linetype = "dashed", linewidth = 0.45, color = "grey35") +
  geom_ribbon(aes(ymin = lower_95, ymax = upper_95), alpha = 0.16, linewidth = 0) +
  geom_line(aes(y = median), linewidth = 1.05) +
  scale_color_manual(values = group_colors[names(group_colors) != "No"]) +
  scale_fill_manual(values = group_colors[names(group_colors) != "No"]) +
  scale_x_continuous(breaks = sort(unique(data$relative_day))) +
  labs(
    title = "App80 organoid-level posterior difference from No",
    x = "Relative day",
    y = "log2(concentration / No)"
  ) +
  guides(fill = "none") +
  base_theme

save_plot(difference_plot, "app80_organoid_level_bayesian_log2_difference_from_no")

probability_plot <- ggplot(difference_summary, aes(x = relative_day, y = probability_smaller_than_control, color = concentration)) +
  geom_hline(yintercept = 0.5, linetype = "dashed", linewidth = 0.45, color = "grey55") +
  geom_hline(yintercept = 0.95, linetype = "dotted", linewidth = 0.45, color = "grey35") +
  geom_line(linewidth = 1.05) +
  scale_color_manual(values = group_colors[names(group_colors) != "No"]) +
  scale_y_continuous(limits = c(0, 1), breaks = seq(0, 1, 0.25)) +
  scale_x_continuous(breaks = sort(unique(data$relative_day))) +
  labs(
    title = "App80 organoid-level probability of smaller area than No",
    x = "Relative day",
    y = "P(concentration < No)"
  ) +
  base_theme

save_plot(probability_plot, "app80_organoid_level_bayesian_probability_smaller_than_no")

rate_density_plot <- ggplot(growth_rate_diff_draws, aes(x = growth_rate_difference_vs_control, color = concentration, fill = concentration)) +
  geom_vline(xintercept = 0, linetype = "dashed", linewidth = 0.45, color = "grey35") +
  geom_density(alpha = 0.18, linewidth = 0.9) +
  scale_color_manual(values = group_colors[names(group_colors) != "No"]) +
  scale_fill_manual(values = group_colors[names(group_colors) != "No"]) +
  labs(
    title = "App80 organoid-level growth-rate difference from No",
    x = "Growth-rate difference, log(area) per day",
    y = "Posterior density"
  ) +
  guides(fill = "none") +
  base_theme

save_plot(rate_density_plot, "app80_organoid_level_bayesian_growth_rate_difference_posteriors")

rate_interval_plot <- ggplot(growth_rate_diff_summary, aes(x = concentration, y = median, color = concentration)) +
  geom_hline(yintercept = 0, linetype = "dashed", linewidth = 0.45, color = "grey35") +
  geom_pointrange(aes(ymin = lower_95, ymax = upper_95), linewidth = 0.7, size = 0.55) +
  scale_color_manual(values = group_colors[names(group_colors) != "No"]) +
  labs(
    title = "App80 organoid-level growth-rate difference summary",
    x = NULL,
    y = "Growth-rate difference vs No"
  ) +
  base_theme +
  theme(legend.position = "none")

save_plot(rate_interval_plot, "app80_organoid_level_bayesian_growth_rate_difference_intervals", width = 6.0, height = 4.4)

diagnostic_summary <- fit_summary %>%
  summarise(
    max_rhat = suppressWarnings(max(rhat, na.rm = TRUE)),
    min_ess_bulk = suppressWarnings(min(ess_bulk, na.rm = TRUE)),
    min_ess_tail = suppressWarnings(min(ess_tail, na.rm = TRUE))
  )
write_csv(diagnostic_summary, file.path(output_dir, "diagnostics", "stan_diagnostic_summary.csv"))

manifest <- list(
  created_at = format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z"),
  input_organoid_metrics = input_path,
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
    response = "log(area_px)",
    formula = "log_organoid_area ~ concentration-specific intercept + concentration-specific slope * relative_day + image random intercept",
    control_group = "No",
    note = "Each segmented organoid is one observation. Image-level random intercepts handle organoids clustered within the same microscopy image."
  ),
  data = list(
    n_organoid_rows = nrow(raw),
    n_used_organoids = nrow(data),
    n_images = length(image_levels),
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
  "# App80 Organoid-Level Bayesian Stan Growth Test",
  "",
  "This folder contains a Stan-based Bayesian growth analysis using each segmented organoid as one observation.",
  "",
  "Sampling unit:",
  "",
  "```text",
  "All organoids from all images/replicates within the same concentration and date are pooled as date-level organoid observations.",
  "```",
  "",
  "Model:",
  "",
  "```text",
  "log(area_px) ~ concentration-specific intercept + concentration-specific slope * relative_day + image random intercept",
  "```",
  "",
  "Control group: `No`.",
  "",
  "Important note: the image random intercept is included to avoid treating organoids from the same image as fully independent technical replicates.",
  "",
  "Key outputs:",
  "",
  "- `figures/app80_organoid_level_bayesian_posterior_growth_curves.png`",
  "- `figures/app80_organoid_level_bayesian_posterior_growth_curves_log_y.png`",
  "- `figures/app80_organoid_level_bayesian_posterior_growth_curves_lines_only.png`",
  "- `figures/app80_organoid_level_bayesian_posterior_growth_curves_lines_only_log_y.png`",
  "- `figures/app80_organoid_level_bayesian_log2_difference_from_no.png`",
  "- `figures/app80_organoid_level_bayesian_probability_smaller_than_no.png`",
  "- `figures/app80_organoid_level_bayesian_growth_rate_difference_posteriors.png`",
  "- `tables/posterior_growth_curve_summary.csv`",
  "- `tables/posterior_log2_difference_from_control_by_day.csv`",
  "- `tables/posterior_growth_rate_difference_vs_control.csv`",
  "- `tables/organoid_counts_by_group_day.csv`",
  "- `tables/image_counts_by_group_day.csv`"
)
writeLines(readme, file.path(output_dir, "README.md"))

message("Completed App80 organoid-level Bayesian Stan growth test: ", output_dir)
