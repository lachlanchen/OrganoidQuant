data {
  int<lower=1> N;
  int<lower=1> G;
  int<lower=1> I;
  array[N] int<lower=1, upper=G> group_id;
  array[N] int<lower=1, upper=I> image_id;
  vector[N] day_scaled;
  vector[N] y;
  real<lower=0> day_sd;
}

parameters {
  vector[G] alpha;
  vector[G] beta_scaled;
  vector[I] image_offset_raw;
  real<lower=0> sigma_image;
  real<lower=0> sigma;
}

transformed parameters {
  vector[I] image_offset = image_offset_raw * sigma_image;
}

model {
  vector[N] mu;

  alpha ~ normal(mean(y), 2);
  beta_scaled ~ normal(0, 1);
  image_offset_raw ~ std_normal();
  sigma_image ~ exponential(1);
  sigma ~ exponential(1);

  for (n in 1:N) {
    mu[n] = alpha[group_id[n]] +
      beta_scaled[group_id[n]] * day_scaled[n] +
      image_offset[image_id[n]];
  }

  y ~ normal(mu, sigma);
}

generated quantities {
  vector[G] beta_per_day;
  vector[N] log_lik;

  for (g in 1:G) {
    beta_per_day[g] = beta_scaled[g] / day_sd;
  }

  for (n in 1:N) {
    log_lik[n] = normal_lpdf(
      y[n] | alpha[group_id[n]] +
        beta_scaled[group_id[n]] * day_scaled[n] +
        image_offset[image_id[n]],
      sigma
    );
  }
}
