# =============================================================================
# scripts/05_regressions.R
# "Do NbS investments reduce economic vulnerability in Gulf cities?"
# Panel: 20 cities x 24 years (2000-2023), two-way FE (city + year)
# Cluster SE by city (G=20); wild Rademacher bootstrap (B=9999)
# Tables: fixest::etable() -> officer (.docx) and type='html' (.html)
# Outcomes: log(elec_pc), ntl_log, industry_va, fdi_pct (M1–M4, a/b specs)
# =============================================================================

suppressPackageStartupMessages({
  library(here)
  library(tidyverse)
  library(fixest)
  library(patchwork)
  library(ggplot2)
  library(officer)
})

PROJ <- here()
PROC <- file.path(PROJ, "data/processed")
TABS <- file.path(PROJ, "outputs/tables")
FIGS <- file.path(PROJ, "outputs/figures")
dir.create(TABS, recursive=TRUE, showWarnings=FALSE)
dir.create(FIGS, recursive=TRUE, showWarnings=FALSE)

SEP <- paste0(rep("=", 68), collapse="")

# ── §1 SETUP & DATA PREP ─────────────────────────────────────────────────────
cat(SEP, "\n§1  SETUP AND DATA PREPARATION\n", SEP, "\n", sep="")

df_raw <- read_csv(file.path(PROC, "master_panel.csv"), show_col_types=FALSE)

df <- df_raw %>%
  mutate(
    sensor_VIIRS    = as.integer(year >= 2013),
    log_elec_pc     = log(elec_pc),
    log_gdp_pc      = log(gdp_pc),
    log_city_pop_th = log(city_pop_th)
  ) %>%
  arrange(city, year) %>%
  group_by(city) %>%
  mutate(
    L1_ndvi = lag(ndvi, 1),
    L2_ndvi = lag(ndvi, 2)
  ) %>%
  ungroup()

cat(sprintf("  N cities  : %d\n", n_distinct(df$city)))
cat(sprintf("  N years   : %d  (%d – %d)\n", n_distinct(df$year), min(df$year), max(df$year)))
cat(sprintf("  N obs     : %d  (balanced: %s)\n", nrow(df),
    if (nrow(df) == n_distinct(df$city) * n_distinct(df$year)) "YES" else "NO"))
cat("\n  Obs by country:\n")
tbl_ctry <- as.data.frame(table(Country=df$country))
for (i in seq_len(nrow(tbl_ctry)))
  cat(sprintf("    %s : %d\n", tbl_ctry$Country[i], tbl_ctry$Freq[i]))

cat("\n  Variable completeness:\n")
for (v in c("ndvi","ntl_log","log_elec_pc","log_gdp_pc","log_city_pop_th",
            "industry_va","fdi_pct","env_exp_pct_gdp","sensor_VIIRS")) {
  n_ok <- sum(!is.na(df[[v]]))
  cat(sprintf("    %-22s %d/%d  (%.1f%%)\n", v, n_ok, nrow(df), 100*n_ok/nrow(df)))
}

# ── §2 MAIN MODELS ───────────────────────────────────────────────────────────
cat("\n", SEP, "\n§2  MAIN MODELS — two-way FE (city + year), cluster SE by city\n", SEP, "\n", sep="")

# sensor_VIIRS is collinear with year FEs; fixest drops it. Year FE subsumes
# the DMSP->VIIRS level shift in M2a/M2b.

m1a <- feols(log_elec_pc ~ ndvi | city + year,
             data=df, cluster=~city, warn=FALSE)
m1b <- feols(log_elec_pc ~ ndvi + log_gdp_pc + log_city_pop_th | city + year,
             data=df, cluster=~city, warn=FALSE)

m2a <- feols(ntl_log ~ ndvi + sensor_VIIRS | city + year,
             data=df, cluster=~city, warn=FALSE)
m2b <- feols(ntl_log ~ ndvi + log_gdp_pc + log_city_pop_th + sensor_VIIRS | city + year,
             data=df, cluster=~city, warn=FALSE)

m3a <- feols(industry_va ~ ndvi | city + year,
             data=df, cluster=~city, warn=FALSE)
m3b <- feols(industry_va ~ ndvi + log_gdp_pc + log_city_pop_th | city + year,
             data=df, cluster=~city, warn=FALSE)

m4a <- feols(fdi_pct ~ ndvi | city + year,
             data=df, cluster=~city, warn=FALSE)
m4b <- feols(fdi_pct ~ ndvi + log_gdp_pc + log_city_pop_th | city + year,
             data=df, cluster=~city, warn=FALSE)

models_main <- list(M1a=m1a, M1b=m1b, M2a=m2a, M2b=m2b,
                    M3a=m3a, M3b=m3b, M4a=m4a, M4b=m4b)

# Restricted formulas for wild bootstrap (H0: beta_ndvi = 0)
formulas_full <- list(
  M1a = log_elec_pc ~ ndvi | city + year,
  M1b = log_elec_pc ~ ndvi + log_gdp_pc + log_city_pop_th | city + year,
  M2a = ntl_log ~ ndvi | city + year,
  M2b = ntl_log ~ ndvi + log_gdp_pc + log_city_pop_th | city + year,
  M3a = industry_va ~ ndvi | city + year,
  M3b = industry_va ~ ndvi + log_gdp_pc + log_city_pop_th | city + year,
  M4a = fdi_pct ~ ndvi | city + year,
  M4b = fdi_pct ~ ndvi + log_gdp_pc + log_city_pop_th | city + year
)
formulas_restr <- list(
  M1a = log_elec_pc ~ 1 | city + year,
  M1b = log_elec_pc ~ log_gdp_pc + log_city_pop_th | city + year,
  M2a = ntl_log ~ 1 | city + year,
  M2b = ntl_log ~ log_gdp_pc + log_city_pop_th | city + year,
  M3a = industry_va ~ 1 | city + year,
  M3b = industry_va ~ log_gdp_pc + log_city_pop_th | city + year,
  M4a = fdi_pct ~ 1 | city + year,
  M4b = fdi_pct ~ log_gdp_pc + log_city_pop_th | city + year
)

# ── §3 WILD CLUSTER BOOTSTRAP ────────────────────────────────────────────────
cat("\n", SEP, "\n§3  WILD CLUSTER BOOTSTRAP (B=9999, Rademacher, cluster by city)\n", SEP, "\n", sep="")
cat("  Note: fwildclusterboot unavailable (needs Rtools). Implemented manually.\n")
cat("  Method: restricted residuals (H0 imposed), cluster-level Rademacher weights.\n\n")

wild_boot <- function(formula_full, formula_restr, data, cluster_col="city",
                      param="ndvi", B=9999, seed=42) {
  set.seed(seed)
  outcome_var <- all.vars(formula_full)[1]

  all_needed <- unique(c(all.vars(formula_full), all.vars(formula_restr),
                         cluster_col, "city", "year"))
  all_needed <- intersect(all_needed, names(data))
  mask <- complete.cases(data[, all_needed])
  dat  <- data[mask, ]

  clusters  <- dat[[cluster_col]]
  unique_cl <- unique(clusters)
  G         <- length(unique_cl)

  m_full  <- feols(formula_full,  data=dat, cluster=as.formula(paste0("~",cluster_col)), warn=FALSE)
  m_restr <- feols(formula_restr, data=dat, cluster=as.formula(paste0("~",cluster_col)), warn=FALSE)

  ct <- tryCatch(coeftable(m_full), error=function(e) NULL)
  if (is.null(ct) || !param %in% rownames(ct))
    return(list(p_val=NA_real_, t_obs=NA_real_, G=G, B=B))

  t_obs   <- ct[param, "Estimate"] / ct[param, "Std. Error"]
  y_hat_r <- fitted(m_restr)
  e_r     <- residuals(m_restr)
  stopifnot(length(e_r) == nrow(dat))

  t_boot <- numeric(B)
  for (b in seq_len(B)) {
    gw <- sample(c(-1L, 1L), G, replace=TRUE)
    ow <- gw[match(clusters, unique_cl)]
    dat_b <- dat
    dat_b[[outcome_var]] <- y_hat_r + e_r * ow
    m_b  <- tryCatch(
      feols(formula_full, data=dat_b,
            cluster=as.formula(paste0("~",cluster_col)), warn=FALSE),
      error=function(e) NULL
    )
    ct_b <- tryCatch(coeftable(m_b), error=function(e) NULL)
    t_boot[b] <- if (!is.null(ct_b) && param %in% rownames(ct_b))
      ct_b[param,"Estimate"] / ct_b[param,"Std. Error"] else NA_real_
  }

  p_val <- mean(abs(t_boot) >= abs(t_obs), na.rm=TRUE)
  list(p_val=p_val, t_obs=t_obs, G=G, B=sum(!is.na(t_boot)))
}

cat("  Running bootstrap (8 models x B=9999) — this may take several minutes...\n")
boot_list <- mapply(wild_boot,
                    formula_full  = formulas_full,
                    formula_restr = formulas_restr,
                    MoreArgs      = list(data=df, cluster_col="city", B=9999, seed=42),
                    SIMPLIFY      = FALSE)

# ── §9 DIAGNOSTIC HELPER ─────────────────────────────────────────────────────
extract_diag <- function(mname, model, boot) {
  ct    <- tryCatch(coeftable(model), error=function(e) NULL)
  ok    <- !is.null(ct) && "ndvi" %in% rownames(ct)
  coef_ <- if (ok) ct["ndvi","Estimate"]   else NA_real_
  se_   <- if (ok) ct["ndvi","Std. Error"] else NA_real_
  pval_ <- if (ok) ct["ndvi","Pr(>|t|)"]  else NA_real_
  r2w_  <- tryCatch(r2(model, type="wr2"), error=function(e) NA_real_)
  bpval <- if (!is.null(boot)) boot$p_val  else NA_real_

  diverge <- !is.na(bpval) && !is.na(pval_) &&
             (max(bpval, pval_) / max(min(bpval, pval_), 1e-6)) > 2
  list(mname=mname, coef=coef_, se=se_, pval=pval_, bpval=bpval,
       r2w=r2w_, nobs=model$nobs, diverge=diverge)
}

# ── §9 MAIN MODEL DIAGNOSTICS ────────────────────────────────────────────────
cat("\n", SEP, "\n§9  DIAGNOSTICS — MAIN MODELS\n", SEP, "\n", sep="")

diag_main <- mapply(extract_diag, names(models_main), models_main, boot_list,
                    SIMPLIFY=FALSE)

for (d in diag_main) {
  cat(sprintf("\n  [%s]  N=%d  G=20 city clusters\n", d$mname, d$nobs))
  cat(sprintf("    ndvi coef   : %+.4f\n", d$coef))
  cat(sprintf("    Cluster SE  : %.4f   |  Cluster p : %.4f\n", d$se, d$pval))
  cat(sprintf("    Wild boot p : %.4f   |  Within R^2: %.4f\n", d$bpval, d$r2w))
  if (d$diverge)
    cat("    *** FLAG [§3]: cluster-p and wild-boot-p diverge by >2x ***\n")
}

full_coefs <- setNames(sapply(diag_main, `[[`, "coef"), names(models_main))

# ── §4 ROBUSTNESS — JACKKNIFE ────────────────────────────────────────────────
cat("\n", SEP, "\n§4  ROBUSTNESS — JACKKNIFE (leave-one-country-out)\n", SEP, "\n", sep="")

countries     <- c("KWT","QAT","ARE","SAU","OMN","BHR")
country_names <- c(KWT="Kuwait",QAT="Qatar",ARE="UAE",
                   SAU="Saudi Arabia",OMN="Oman",BHR="Bahrain")

jk_results <- map_dfr(countries, function(drop_iso) {
  df_jk <- df %>% filter(country != drop_iso)
  jk_mods <- list(
    M1a = feols(log_elec_pc ~ ndvi | city + year, data=df_jk, cluster=~city, warn=FALSE),
    M1b = feols(log_elec_pc ~ ndvi + log_gdp_pc + log_city_pop_th | city + year,
                data=df_jk, cluster=~city, warn=FALSE),
    M2a = feols(ntl_log ~ ndvi | city + year, data=df_jk, cluster=~city, warn=FALSE),
    M2b = feols(ntl_log ~ ndvi + log_gdp_pc + log_city_pop_th | city + year,
                data=df_jk, cluster=~city, warn=FALSE),
    M3a = feols(industry_va ~ ndvi | city + year, data=df_jk, cluster=~city, warn=FALSE),
    M3b = feols(industry_va ~ ndvi + log_gdp_pc + log_city_pop_th | city + year,
                data=df_jk, cluster=~city, warn=FALSE),
    M4a = feols(fdi_pct ~ ndvi | city + year, data=df_jk, cluster=~city, warn=FALSE),
    M4b = feols(fdi_pct ~ ndvi + log_gdp_pc + log_city_pop_th | city + year,
                data=df_jk, cluster=~city, warn=FALSE)
  )
  map_dfr(names(jk_mods), function(mn) {
    ct <- tryCatch(coeftable(jk_mods[[mn]]), error=function(e) NULL)
    if (is.null(ct) || !"ndvi" %in% rownames(ct))
      return(tibble(dropped_iso=drop_iso, dropped_name=country_names[drop_iso],
                    model=mn, coef=NA_real_, se=NA_real_, pval=NA_real_))
    tibble(dropped_iso=drop_iso, dropped_name=country_names[drop_iso], model=mn,
           coef=ct["ndvi","Estimate"], se=ct["ndvi","Std. Error"],
           pval=ct["ndvi","Pr(>|t|)"])
  })
})

cat("\n  Full-sample ndvi coefficients:\n")
for (mn in names(full_coefs))
  cat(sprintf("    %s : %+.4f\n", mn, full_coefs[mn]))

cat("\n  Jackknife range and max % change from full-sample:\n")
jk_summary <- jk_results %>%
  group_by(model) %>%
  summarise(coef_min=min(coef, na.rm=TRUE), coef_max=max(coef, na.rm=TRUE), .groups="drop") %>%
  mutate(coef_full = full_coefs[model],
         pct_max   = 100 * pmax(abs(coef_max-coef_full), abs(coef_min-coef_full)) /
                     pmax(abs(coef_full), 1e-10),
         flag_50   = pct_max > 50)

for (i in seq_len(nrow(jk_summary))) {
  r <- jk_summary[i,]
  cat(sprintf("    %s : full=%+.4f  range=[%+.4f, %+.4f]  maxDelta=%.0f%%%s\n",
      r$model, r$coef_full, r$coef_min, r$coef_max, r$pct_max,
      if (r$flag_50) "  *** FLAG: >50% change ***" else ""))
}

cat("\n  Most influential country per model:\n")
jk_infl <- jk_results %>%
  left_join(tibble(model=names(full_coefs), coef_full=full_coefs), by="model") %>%
  mutate(pct_chg = 100 * abs(coef - coef_full) / pmax(abs(coef_full), 1e-10)) %>%
  group_by(model) %>% slice_max(pct_chg, n=1) %>% ungroup()

for (i in seq_len(nrow(jk_infl))) {
  r    <- jk_infl[i,]
  flag <- jk_summary$flag_50[jk_summary$model==r$model]
  cat(sprintf("    %s : dropping %s changes coef by %.1f%%%s\n",
      r$model, r$dropped_name, r$pct_chg,
      if(isTRUE(flag)) "  *** FLAG ***" else ""))
}

# ── §5 ROBUSTNESS — VIIRS-ONLY SUBSAMPLE ─────────────────────────────────────
cat("\n", SEP, "\n§5  ROBUSTNESS — VIIRS-ONLY SUBSAMPLE (2013-2023)\n", SEP, "\n", sep="")

df_viirs <- df %>% filter(year >= 2013)
cat(sprintf("  N obs (VIIRS-only) : %d  (%d cities x 11 years)\n\n",
    nrow(df_viirs), n_distinct(df_viirs$city)))

v_models <- list(
  M1a = feols(log_elec_pc ~ ndvi | city + year, data=df_viirs, cluster=~city, warn=FALSE),
  M1b = feols(log_elec_pc ~ ndvi + log_gdp_pc + log_city_pop_th | city + year,
              data=df_viirs, cluster=~city, warn=FALSE),
  M2a = feols(ntl_log ~ ndvi | city + year, data=df_viirs, cluster=~city, warn=FALSE),
  M2b = feols(ntl_log ~ ndvi + log_gdp_pc + log_city_pop_th | city + year,
              data=df_viirs, cluster=~city, warn=FALSE),
  M3a = feols(industry_va ~ ndvi | city + year, data=df_viirs, cluster=~city, warn=FALSE),
  M3b = feols(industry_va ~ ndvi + log_gdp_pc + log_city_pop_th | city + year,
              data=df_viirs, cluster=~city, warn=FALSE),
  M4a = feols(fdi_pct ~ ndvi | city + year, data=df_viirs, cluster=~city, warn=FALSE),
  M4b = feols(fdi_pct ~ ndvi + log_gdp_pc + log_city_pop_th | city + year,
              data=df_viirs, cluster=~city, warn=FALSE)
)

cat(sprintf("  %-6s  %+10s  %+10s  %10s  %s\n",
    "Model","Full coef","VIIRS coef","VIIRS p","Sign flip?"))
cat(paste0(rep("-", 58), collapse=""), "\n")
for (mn in names(v_models)) {
  ct <- tryCatch(coeftable(v_models[[mn]]), error=function(e) NULL)
  if (is.null(ct) || !"ndvi" %in% rownames(ct)) next
  cv   <- ct["ndvi","Estimate"]
  cf   <- full_coefs[mn]
  pvv  <- ct["ndvi","Pr(>|t|)"]
  flip <- sign(cv) != sign(cf)
  cat(sprintf("  %-6s  %+10.4f  %+10.4f  %10.4f  %s\n",
      mn, cf, cv, pvv,
      if(flip) "*** SIGN FLIP ***" else "No"))
}

# ── §6 ROBUSTNESS — LAGGED NDVI ──────────────────────────────────────────────
cat("\n", SEP, "\n§6  ROBUSTNESS — LAGGED NDVI (L1 and L2)\n", SEP, "\n", sep="")

lag_results <- map_dfr(c("L1_ndvi","L2_ndvi"), function(lag_var) {
  lag_lbl <- if (lag_var=="L1_ndvi") "L1 (1-yr)" else "L2 (2-yr)"
  fmls <- list(
    "log(elec/cap)" = as.formula(paste0("log_elec_pc ~ ", lag_var, " | city + year")),
    "ntl_log"       = as.formula(paste0("ntl_log ~ ",     lag_var, " | city + year")),
    "industry_va"   = as.formula(paste0("industry_va ~ ", lag_var, " | city + year")),
    "fdi_pct"       = as.formula(paste0("fdi_pct ~ ",     lag_var, " | city + year"))
  )
  map_dfr(names(fmls), function(out) {
    m  <- feols(fmls[[out]], data=df, cluster=~city, warn=FALSE)
    ct <- tryCatch(coeftable(m), error=function(e) NULL)
    if (is.null(ct) || !lag_var %in% rownames(ct)) return(NULL)
    tibble(lag=lag_lbl, outcome=out,
           coef=ct[lag_var,"Estimate"], se=ct[lag_var,"Std. Error"],
           pval=ct[lag_var,"Pr(>|t|)"], nobs=m$nobs)
  })
})

cat(sprintf("  %-10s  %-16s  %+10s  %10s  %10s  %6s\n",
    "Lag","Outcome","coef","SE","p-val","N"))
cat(paste0(rep("-", 68), collapse=""), "\n")
for (i in seq_len(nrow(lag_results))) {
  r <- lag_results[i,]
  cat(sprintf("  %-10s  %-16s  %+10.4f  %10.4f  %10.4f  %6d\n",
      r$lag, r$outcome, r$coef, r$se, r$pval, r$nobs))
}

# ── §7 ROBUSTNESS — ENV EXPENDITURE SUBSAMPLE ────────────────────────────────
cat("\n", SEP, "\n§7  ROBUSTNESS — ENV EXPENDITURE SUBSAMPLE\n", SEP, "\n", sep="")

df_env <- df %>% filter(!is.na(env_exp_pct_gdp))
cat(sprintf("  N obs: %d | Countries: %s\n",
    nrow(df_env), paste(unique(df_env$country), collapse=", ")))
cat(sprintf("  (SAU entirely absent; env_exp available for KWT, QAT, ARE, OMN, BHR)\n\n"))

env_models <- list(
  M1a = feols(log_elec_pc ~ ndvi | city + year, data=df_env, cluster=~city, warn=FALSE),
  M2a = feols(ntl_log ~ ndvi | city + year,     data=df_env, cluster=~city, warn=FALSE),
  M3a = feols(industry_va ~ ndvi | city + year, data=df_env, cluster=~city, warn=FALSE),
  M4a = feols(fdi_pct ~ ndvi | city + year,     data=df_env, cluster=~city, warn=FALSE)
)

cat(sprintf("  %-6s  %+10s  %+10s  %10s  %8s\n",
    "Model","Full coef","Env coef","Env p","N env"))
cat(paste0(rep("-", 52), collapse=""), "\n")
for (mn in names(env_models)) {
  ct <- tryCatch(coeftable(env_models[[mn]]), error=function(e) NULL)
  if (is.null(ct) || !"ndvi" %in% rownames(ct)) next
  cat(sprintf("  %-6s  %+10.4f  %+10.4f  %10.4f  %8d\n",
      mn, full_coefs[mn], ct["ndvi","Estimate"],
      ct["ndvi","Pr(>|t|)"], env_models[[mn]]$nobs))
}

# ── §M4 FULL DIAGNOSTICS — FDI MODELS ───────────────────────────────────────
cat("\n", SEP, "\n§M4  FULL DIAGNOSTICS — FDI OUTCOME (M4a and M4b)\n", SEP, "\n", sep="")
cat("  Specification: fdi_pct (net inflows, % GDP) ~ NDVI | city + year\n")

for (mn in c("M4a","M4b")) {
  d    <- diag_main[[mn]]
  jk_r <- jk_summary %>% filter(model == mn)

  vct        <- tryCatch(coeftable(v_models[[mn]]), error=function(e) NULL)
  v_ok       <- !is.null(vct) && "ndvi" %in% rownames(vct)
  viirs_coef <- if (v_ok) vct["ndvi","Estimate"] else NA_real_
  viirs_flip <- v_ok && (sign(viirs_coef) != sign(d$coef))

  l1_row  <- lag_results %>% filter(lag=="L1 (1-yr)", outcome=="fdi_pct")
  l2_row  <- lag_results %>% filter(lag=="L2 (2-yr)", outcome=="fdi_pct")
  l1_coef <- if (nrow(l1_row)>0) l1_row$coef[1] else NA_real_
  l2_coef <- if (nrow(l2_row)>0) l2_row$coef[1] else NA_real_
  l1_pval <- if (nrow(l1_row)>0) l1_row$pval[1] else NA_real_
  l2_pval <- if (nrow(l2_row)>0) l2_row$pval[1] else NA_real_

  spec_str <- if (mn=="M4b") " + log(gdp_pc) + log(city_pop_th)" else ""
  cat(sprintf("\n  ── %s : fdi_pct ~ ndvi%s | city + year ──\n", mn, spec_str))
  cat(sprintf("    N obs              : %d  (G=20 city clusters)\n", d$nobs))
  cat(sprintf("    NDVI coef          : %+.4f\n", d$coef))
  cat(sprintf("    Cluster SE         : %.4f\n", d$se))
  cat(sprintf("    Cluster p          : %.4f%s\n", d$pval,
      if (!is.na(d$pval) && d$pval < 0.01) "  ***"
      else if (!is.na(d$pval) && d$pval < 0.05) "  **"
      else if (!is.na(d$pval) && d$pval < 0.10) "  *"
      else ""))
  cat(sprintf("    Wild boot p (9999) : %.4f%s\n", d$bpval,
      if (!is.na(d$bpval) && d$bpval < 0.01) "  ***"
      else if (!is.na(d$bpval) && d$bpval < 0.05) "  **"
      else if (!is.na(d$bpval) && d$bpval < 0.10) "  *"
      else ""))
  cat(sprintf("    Within R²          : %.4f\n", d$r2w))
  if (d$diverge)
    cat("    *** FLAG: cluster-p and wild-boot-p diverge by >2x ***\n")
  if (nrow(jk_r) > 0)
    cat(sprintf("    Jackknife max Δ%%  : %.1f%%  (%s)\n",
        jk_r$pct_max,
        if (jk_r$flag_50) "*** FLAG: >50% change ***" else "stable"))
  cat(sprintf("    VIIRS-only coef    : %s\n",
      if (is.na(viirs_coef)) "NA"
      else sprintf("%+.4f  (sign flip: %s)", viirs_coef,
                   if (viirs_flip) "*** YES ***" else "No")))
  cat(sprintf("    Lagged NDVI L1     : %s\n",
      if (is.na(l1_coef)) "NA"
      else sprintf("%+.4f  (p=%.4f)", l1_coef, l1_pval)))
  cat(sprintf("    Lagged NDVI L2     : %s\n",
      if (is.na(l2_coef)) "NA"
      else sprintf("%+.4f  (p=%.4f)", l2_coef, l2_pval)))
}

# ── §8 OUTPUTS ────────────────────────────────────────────────────────────────
cat("\n", SEP, "\n§8  SAVING OUTPUTS\n", SEP, "\n", sep="")

write_docx <- function(df, path, title=NULL, notes=NULL) {
  doc <- officer::read_docx()
  if (!is.null(title))
    doc <- officer::body_add_par(doc, title, style="heading 2")
  doc <- officer::body_add_table(doc, as.data.frame(df))
  if (!is.null(notes))
    doc <- officer::body_add_par(doc, notes, style="Normal")
  print(doc, target=path)
  invisible(path)
}

# -- 8.1  Main results table (.docx and .html) --------------------------------
boot_pvals_fmt <- setNames(
  sapply(boot_list, function(b)
    if (!is.null(b) && !is.na(b$p_val)) formatC(b$p_val, digits=3, format="f") else "NA"),
  names(boot_list)
)

etable_args <- list(
  coefstat    = "se",
  signif.code = c("***"=0.01, "**"=0.05, "*"=0.10),
  digits      = 4,
  dict        = c(ndvi="NDVI",
                  log_gdp_pc="log(GDP/cap)",
                  log_city_pop_th="log(City pop)"),
  fitstat     = c("n", "wr2"),
  extralines  = list("Wild Bootstrap p (NDVI)" = unname(boot_pvals_fmt))
)

tryCatch({
  tbl_main_df <- do.call(etable, c(models_main, etable_args, list(tex=FALSE)))
  write_docx(
    tbl_main_df,
    path  = file.path(TABS, "main_results.docx"),
    title = "NDVI and Economic Outcomes in Gulf Cities (Two-Way FE, 2000-2023)",
    notes = paste("Cluster-robust SE by city (G=20).",
                  "Wild bootstrap p-values (B=9999, Rademacher, H0 imposed).",
                  "Two-way FE: city + year.",
                  "Outcomes: log(elec_pc) [M1], ntl_log [M2], industry_va [M3], fdi_pct [M4].")
  )
  cat("  Saved: main_results.docx\n")
}, error=function(e) cat("  ERROR saving main_results.docx:", conditionMessage(e), "\n"))

tryCatch({
  tbl_df  <- do.call(etable, c(models_main, etable_args, list(tex=FALSE)))
  df_rows <- apply(tbl_df, 1, function(r)
    paste0("  <tr>", paste0("<td>", r, "</td>", collapse=""), "</tr>")
  )
  html_body <- paste0(c(
    "<!DOCTYPE html><html><head><meta charset='utf-8'>",
    "<style>table{border-collapse:collapse;font-family:sans-serif;font-size:13px}",
    "td,th{border:1px solid #ccc;padding:4px 8px}th{background:#f0f0f0}</style>",
    "<title>Gulf NBS Main Results</title></head><body>",
    "<h2>NDVI and Economic Outcomes in Gulf Cities (Two-Way FE, 2000-2023)</h2>",
    "<table>",
    paste0("  <tr>", paste0("<th>", names(tbl_df), "</th>", collapse=""), "</tr>"),
    df_rows,
    "</table>",
    "<p><em>Cluster-robust SE by city (G=20). Wild bootstrap p-values (B=9999, Rademacher, H0 imposed). ",
    "Two-way FE: city + year. Outcomes: log(elec_pc) [M1], ntl_log [M2], industry_va [M3], fdi_pct [M4].</em></p>",
    "</body></html>"
  ), collapse="\n")
  writeLines(html_body, file.path(TABS, "main_results.html"))
  cat("  Saved: main_results.html\n")
}, error=function(e) cat("  ERROR saving main_results.html:", conditionMessage(e), "\n"))

# -- 8.2  Jackknife table (.docx) ---------------------------------------------
jk_wide <- jk_results %>%
  mutate(cell = sprintf("%+.3f (%.3f)", coef, se)) %>%
  select(dropped_name, model, cell) %>%
  pivot_wider(names_from=model, values_from=cell) %>%
  rename(Country=dropped_name)

tryCatch({
  write_docx(
    jk_wide,
    path  = file.path(TABS, "robustness_jackknife.docx"),
    title = "Jackknife Robustness: NDVI Coefficient (Leave-One-Country-Out)",
    notes = "Format: coef (SE). Each row drops one GCC country from the estimation sample."
  )
  cat("  Saved: robustness_jackknife.docx\n")
}, error=function(e) cat("  ERROR saving jackknife table:", conditionMessage(e), "\n"))

# -- 8.3  Robustness subsamples table (.docx) ---------------------------------
viirs_rows <- map_dfr(names(v_models), function(mn) {
  ct <- tryCatch(coeftable(v_models[[mn]]), error=function(e) NULL)
  if (is.null(ct) || !"ndvi" %in% rownames(ct)) return(NULL)
  tibble(Subsample="VIIRS-only (2013-23)", Model=mn,
         `Full coef`=sprintf("%+.4f", full_coefs[mn]),
         `Sub coef`=sprintf("%+.4f", ct["ndvi","Estimate"]),
         SE=sprintf("%.4f", ct["ndvi","Std. Error"]),
         `p-val`=sprintf("%.4f", ct["ndvi","Pr(>|t|)"]),
         N=as.character(v_models[[mn]]$nobs))
})

lag_rows <- lag_results %>%
  transmute(
    Subsample=paste0("Lagged: ", lag), Model=outcome,
    `Full coef`="(contemp.)", `Sub coef`=sprintf("%+.4f",coef),
    SE=sprintf("%.4f",se), `p-val`=sprintf("%.4f",pval), N=as.character(nobs)
  )

env_rows <- map_dfr(names(env_models), function(mn) {
  ct <- tryCatch(coeftable(env_models[[mn]]), error=function(e) NULL)
  if (is.null(ct) || !"ndvi" %in% rownames(ct)) return(NULL)
  tibble(Subsample="Env exp (non-NA)", Model=mn,
         `Full coef`=sprintf("%+.4f", full_coefs[mn]),
         `Sub coef`=sprintf("%+.4f", ct["ndvi","Estimate"]),
         SE=sprintf("%.4f", ct["ndvi","Std. Error"]),
         `p-val`=sprintf("%.4f", ct["ndvi","Pr(>|t|)"]),
         N=as.character(env_models[[mn]]$nobs))
})

rob_table <- bind_rows(viirs_rows, lag_rows, env_rows)

tryCatch({
  write_docx(
    rob_table,
    path  = file.path(TABS, "robustness_subsamples.docx"),
    title = "Robustness Checks: NDVI Coefficient Across Subsamples and Lag Structures",
    notes = "Full coef = contemporaneous full-sample estimate. Sub coef = subsample or lagged estimate."
  )
  cat("  Saved: robustness_subsamples.docx\n")
}, error=function(e) cat("  ERROR saving robustness table:", conditionMessage(e), "\n"))

# -- 8.4  Main coefficient plot (8 models: 4 outcomes x 2 specs) -------------
coef_plot_df <- map_dfr(names(models_main), function(mn) {
  ct <- tryCatch(coeftable(models_main[[mn]]), error=function(e) NULL)
  if (is.null(ct) || !"ndvi" %in% rownames(ct)) return(NULL)
  b   <- ct["ndvi","Estimate"]
  se  <- ct["ndvi","Std. Error"]
  bpv <- boot_list[[mn]]$p_val
  tibble(
    model   = mn,
    coef    = b,
    se      = se,
    ci_lo   = b - 1.96*se,
    ci_hi   = b + 1.96*se,
    pval_cl = ct["ndvi","Pr(>|t|)"],
    pval_wc = bpv,
    outcome = case_when(
      mn %in% c("M1a","M1b") ~ "log(elec/capita)",
      mn %in% c("M2a","M2b") ~ "log(1+NTL)",
      mn %in% c("M3a","M3b") ~ "industry_va (% GDP)",
      TRUE                    ~ "FDI (% GDP)"
    ),
    spec = if_else(mn %in% c("M1a","M2a","M3a","M4a"), "Bivariate", "Full controls"),
    sig_label = case_when(
      pval_wc < 0.01 ~ "p<0.01 (WCB)",
      pval_wc < 0.05 ~ "p<0.05 (WCB)",
      pval_wc < 0.10 ~ "p<0.10 (WCB)",
      TRUE           ~ "n.s."
    )
  )
})

palette_out <- c(
  "log(elec/capita)"    = "#2D7DA8",
  "log(1+NTL)"          = "#D85A30",
  "industry_va (% GDP)" = "#C8A02C",
  "FDI (% GDP)"         = "#5B9E6E"
)

p_coef <- ggplot(coef_plot_df,
                 aes(x=model, y=coef, color=outcome, shape=spec)) +
  geom_hline(yintercept=0, linetype="dashed", color="grey60", linewidth=0.6) +
  geom_pointrange(aes(ymin=ci_lo, ymax=ci_hi),
                  size=0.9, linewidth=1.1, position=position_dodge(0)) +
  geom_text(aes(label=sig_label, y=ci_hi), vjust=-0.7, size=2.8,
            color="grey30", fontface="italic") +
  scale_color_manual(values=palette_out) +
  scale_shape_manual(values=c("Bivariate"=16, "Full controls"=17)) +
  labs(
    title    = "NDVI Coefficient Across Main Specifications",
    subtitle = "Two-way FE (city+year), cluster-robust 95% CI (G=20). Significance from wild cluster bootstrap (B=9999).",
    x="Model", y="Coefficient on NDVI",
    color="Outcome", shape="Specification"
  ) +
  theme_minimal(base_size=12) +
  theme(plot.title=element_text(face="bold"),
        legend.position="bottom",
        plot.subtitle=element_text(color="grey40", size=9))

ggsave(file.path(FIGS, "main_coefplot.png"), p_coef,
       width=13, height=6.5, dpi=150)
cat("  Saved: main_coefplot.png\n")

# -- 8.5  Jackknife distribution plot (8 models, 4-column grid) ---------------
jk_plot_df <- jk_results %>%
  left_join(tibble(model=names(full_coefs), coef_full=full_coefs), by="model") %>%
  mutate(dropped_name = factor(dropped_name,
    levels=c("Kuwait","Qatar","UAE","Bahrain","Oman","Saudi Arabia")))

p_jk <- ggplot(jk_plot_df,
               aes(x=dropped_name, y=coef, color=model, group=model)) +
  geom_hline(aes(yintercept=coef_full), linetype="dashed",
             color="grey40", linewidth=0.7) +
  geom_pointrange(aes(ymin=coef-1.96*se, ymax=coef+1.96*se),
                  position=position_dodge(width=0.6), size=0.6, linewidth=0.9) +
  geom_hline(yintercept=0, color="black", linewidth=0.4) +
  facet_wrap(~model, scales="free_y", ncol=4) +
  scale_color_manual(values=c(
    M1a="#2D7DA8", M1b="#5FAFD1",
    M2a="#D85A30", M2b="#E8916A",
    M3a="#C8A02C", M3b="#DFC06A",
    M4a="#5B9E6E", M4b="#8FCA9F"
  )) +
  labs(
    title    = "Jackknife Robustness: NDVI Coefficient (Leave-One-Country-Out)",
    subtitle = "Dashed line = full-sample estimate. Bars = 95% cluster-robust CI (G-1 clusters).",
    x="Country dropped", y="ndvi coefficient"
  ) +
  theme_minimal(base_size=11) +
  theme(axis.text.x=element_text(angle=45, hjust=1),
        legend.position="none",
        plot.title=element_text(face="bold"),
        strip.text=element_text(face="bold"))

ggsave(file.path(FIGS, "jackknife_distribution.png"), p_jk,
       width=18, height=9, dpi=150)
cat("  Saved: jackknife_distribution.png\n")

# ── FINAL SUMMARY ─────────────────────────────────────────────────────────────
cat("\n", SEP, "\n  FINAL ROBUSTNESS SUMMARY — ALL 8 MODELS\n", SEP, "\n", sep="")
cat("  Pass criteria: (1) wild-boot p < 0.10, (2) no VIIRS sign flip, (3) jackknife max Δ < 50%\n")

cat(sprintf("\n  %-6s  %-12s  %-14s  %-16s  %-14s  %s\n",
    "Model","Cluster p","Wild boot p","Sign flip VIIRS?","Jackknife flag","Status"))
cat(paste0(rep("-", 80), collapse=""), "\n")

surviving <- character(0)
for (mn in names(models_main)) {
  d    <- diag_main[[mn]]
  vct  <- tryCatch(coeftable(v_models[[mn]]), error=function(e) NULL)
  v_ok <- !is.null(vct) && "ndvi" %in% rownames(vct)
  flip <- v_ok && (sign(vct["ndvi","Estimate"]) != sign(full_coefs[mn]))
  jk_f <- jk_summary$flag_50[jk_summary$model==mn]

  pass <- !d$diverge && !isTRUE(flip) && !isTRUE(jk_f)
  if (pass) surviving <- c(surviving, mn)
  cat(sprintf("  %-6s  %-12s  %-14s  %-16s  %-14s  %s\n",
      mn,
      sprintf("%.3f", d$pval),
      sprintf("%.3f", d$bpval),
      if(isTRUE(flip)) "YES ***" else "No",
      if(isTRUE(jk_f)) "YES ***" else "No",
      if(pass) "PASS" else "FAIL"))
}

cat(sprintf("\n  Models surviving all robustness checks: %s\n",
    if (length(surviving)==0) "none" else paste(surviving, collapse=", ")))

cat("\n", SEP, "\nSCRIPT COMPLETE\n", SEP, "\n", sep="")
