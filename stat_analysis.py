import json
import numpy as np
from scipy import stats

# Load data
with open(r"c:/Users/danil/OneDrive/Рабочий стол/Felex_v1/.claude/benchmarks/results/benchmark_results.json", "r", encoding="utf-8") as f:
    data = json.load(f)

cases = data["benchmark"]["cases"]
print(f"Number of cases: {len(cases)}")

# Extract norm_coverage_index and runtime_ms for each workflow type
build_coverage = []
complete_coverage = []
selected_coverage = []

build_runtime = []
complete_runtime = []
selected_runtime = []

build_cost = []
complete_cost = []
selected_cost = []

build_hard_pass = []
complete_hard_pass = []
selected_hard_pass = []

for case in cases:
    case_id = case["case"]["id"]
    for wf in case["workflows"]:
        intent = wf["intent"]
        nci = wf.get("norm_coverage_index")
        rt = wf.get("runtime_ms")
        cost = wf.get("cost_per_day_rub")
        hpr = wf.get("hard_pass_rate")

        if intent == "build_from_library":
            build_coverage.append(nci)
            build_runtime.append(rt)
            build_cost.append(cost)
            build_hard_pass.append(hpr)
        elif intent == "complete_from_library":
            complete_coverage.append(nci)
            complete_runtime.append(rt)
            complete_cost.append(cost)
            complete_hard_pass.append(hpr)
        elif intent == "selected_only":
            selected_coverage.append(nci)
            selected_runtime.append(rt)
            selected_cost.append(cost)
            selected_hard_pass.append(hpr)

print(f"build_from_library: n={len(build_coverage)}")
print(f"complete_from_library: n={len(complete_coverage)}")
print(f"selected_only: n={len(selected_coverage)}")

# Convert to arrays
build_cov = np.array(build_coverage)
complete_cov = np.array(complete_coverage)
selected_cov = np.array(selected_coverage)

print("\n" + "="*80)
print("DESCRIPTIVE STATISTICS: norm_coverage_index")
print("="*80)
for name, arr in [("build_from_library", build_cov), ("complete_from_library", complete_cov), ("selected_only", selected_cov)]:
    print(f"\n{name}:")
    print(f"  n = {len(arr)}")
    print(f"  Mean = {np.mean(arr):.4f}")
    print(f"  SD   = {np.std(arr, ddof=1):.4f}")
    print(f"  Median = {np.median(arr):.4f}")
    print(f"  Min  = {np.min(arr):.4f}")
    print(f"  Max  = {np.max(arr):.4f}")
    q1, q3 = np.percentile(arr, [25, 75])
    print(f"  Q1   = {q1:.4f}")
    print(f"  Q3   = {q3:.4f}")
    print(f"  IQR  = {q3 - q1:.4f}")

# Paired differences
diff = complete_cov - build_cov
print(f"\n\nPaired differences (complete - build):")
print(f"  Mean diff = {np.mean(diff):.4f}")
print(f"  SD diff   = {np.std(diff, ddof=1):.4f}")
print(f"  Median diff = {np.median(diff):.4f}")

# ============================================================
# 1. Paired Wilcoxon signed-rank test
# ============================================================
print("\n" + "="*80)
print("1. PAIRED WILCOXON SIGNED-RANK TEST")
print("   H0: median difference = 0")
print("   H1: median difference != 0 (two-sided)")
print("="*80)

wilcoxon_result = stats.wilcoxon(complete_cov, build_cov, alternative='two-sided')
print(f"  Test statistic W = {wilcoxon_result.statistic:.4f}")
print(f"  p-value = {wilcoxon_result.pvalue:.6f}")

if wilcoxon_result.pvalue < 0.001:
    sig_interp = "highly significant (p < 0.001)"
elif wilcoxon_result.pvalue < 0.01:
    sig_interp = "significant (p < 0.01)"
elif wilcoxon_result.pvalue < 0.05:
    sig_interp = "significant (p < 0.05)"
else:
    sig_interp = "not significant (p >= 0.05)"
print(f"  Interpretation: {sig_interp}")

# ============================================================
# 2. Paired t-test
# ============================================================
print("\n" + "="*80)
print("2. PAIRED t-TEST")
print("   H0: mean difference = 0")
print("   H1: mean difference != 0 (two-sided)")
print("="*80)

ttest_result = stats.ttest_rel(complete_cov, build_cov)
print(f"  t-statistic = {ttest_result.statistic:.4f}")
print(f"  p-value = {ttest_result.pvalue:.6f}")
print(f"  df = {len(diff) - 1}")

# 95% CI for mean difference
mean_diff = np.mean(diff)
se_diff = stats.sem(diff)
t_crit = stats.t.ppf(0.975, df=len(diff)-1)
ci_low = mean_diff - t_crit * se_diff
ci_high = mean_diff + t_crit * se_diff
print(f"  Mean difference = {mean_diff:.4f}")
print(f"  SE = {se_diff:.4f}")
print(f"  95% CI = [{ci_low:.4f}, {ci_high:.4f}]")

if ttest_result.pvalue < 0.001:
    sig_interp_t = "highly significant (p < 0.001)"
elif ttest_result.pvalue < 0.01:
    sig_interp_t = "significant (p < 0.01)"
elif ttest_result.pvalue < 0.05:
    sig_interp_t = "significant (p < 0.05)"
else:
    sig_interp_t = "not significant (p >= 0.05)"
print(f"  Interpretation: {sig_interp_t}")

# ============================================================
# 3. Cohen's d effect size
# ============================================================
print("\n" + "="*80)
print("3. COHEN'S d EFFECT SIZE (paired)")
print("="*80)

d = mean_diff / np.std(diff, ddof=1)
print(f"  d = mean_diff / SD_diff = {mean_diff:.4f} / {np.std(diff, ddof=1):.4f} = {d:.4f}")

if abs(d) >= 0.8:
    d_interp = "large"
elif abs(d) >= 0.5:
    d_interp = "medium"
elif abs(d) >= 0.2:
    d_interp = "small"
else:
    d_interp = "negligible"
print(f"  Interpretation: |d| = {abs(d):.4f} => {d_interp} effect")

# ============================================================
# 4. Bootstrap 95% CI
# ============================================================
print("\n" + "="*80)
print("4. BOOTSTRAP 95% CI FOR MEAN DIFFERENCE")
print("   10,000 bootstrap resamples of the 23 paired differences")
print("="*80)

np.random.seed(42)
n_boot = 10000
boot_means = np.zeros(n_boot)
n = len(diff)
for i in range(n_boot):
    sample = np.random.choice(diff, size=n, replace=True)
    boot_means[i] = np.mean(sample)

boot_ci_low = np.percentile(boot_means, 2.5)
boot_ci_high = np.percentile(boot_means, 97.5)
print(f"  Bootstrap mean of differences = {np.mean(boot_means):.4f}")
print(f"  Bootstrap SD = {np.std(boot_means):.4f}")
print(f"  Bootstrap 95% CI = [{boot_ci_low:.4f}, {boot_ci_high:.4f}]")

# ============================================================
# 5. Runtime descriptive statistics per workflow
# ============================================================
print("\n" + "="*80)
print("5. RUNTIME DESCRIPTIVE STATISTICS (ms) PER WORKFLOW")
print("   Note: across-scenario statistics, not repeated-trial")
print("="*80)

for name, arr_list in [("selected_only", selected_runtime),
                        ("build_from_library", build_runtime),
                        ("complete_from_library", complete_runtime)]:
    arr = np.array(arr_list)
    q1, q3 = np.percentile(arr, [25, 75])
    print(f"\n{name}:")
    print(f"  n      = {len(arr)}")
    print(f"  Mean   = {np.mean(arr):.4f} ms")
    print(f"  SD     = {np.std(arr, ddof=1):.4f} ms")
    print(f"  Median = {np.median(arr):.4f} ms")
    print(f"  Q1     = {q1:.4f} ms")
    print(f"  Q3     = {q3:.4f} ms")
    print(f"  IQR    = {q3 - q1:.4f} ms")
    print(f"  Min    = {np.min(arr):.4f} ms")
    print(f"  Max    = {np.max(arr):.4f} ms")

# ============================================================
# 6. Sign test
# ============================================================
print("\n" + "="*80)
print("6. SIGN TEST: complete > build coverage")
print("="*80)

n_positive = int(np.sum(diff > 0))
n_negative = int(np.sum(diff < 0))
n_zero = int(np.sum(diff == 0))
n_nonzero = n_positive + n_negative

print(f"  complete > build:  {n_positive} / {len(diff)} scenarios")
print(f"  complete < build:  {n_negative} / {len(diff)} scenarios")
print(f"  complete == build: {n_zero} / {len(diff)} scenarios")
print(f"  Proportion (complete > build) = {n_positive / len(diff):.4f}")

# Binomial test (sign test) - under H0, p(positive) = 0.5
sign_test = stats.binomtest(n_positive, n_nonzero, p=0.5, alternative='two-sided')
print(f"  Sign test p-value = {sign_test.pvalue:.6f}")
if sign_test.pvalue < 0.05:
    print(f"  Interpretation: Significant -- complete_from_library consistently differs from build_from_library")
else:
    print(f"  Interpretation: Not significant -- no consistent directional difference")

# ============================================================
# Cost descriptive stats
# ============================================================
print("\n" + "="*80)
print("COST DESCRIPTIVE STATISTICS (RUB/day) PER WORKFLOW")
print("="*80)

for name, arr_list in [("selected_only", selected_cost),
                        ("build_from_library", build_cost),
                        ("complete_from_library", complete_cost)]:
    arr = np.array(arr_list)
    q1, q3 = np.percentile(arr, [25, 75])
    print(f"\n{name}:")
    print(f"  Mean   = {np.mean(arr):.2f} RUB/day")
    print(f"  SD     = {np.std(arr, ddof=1):.2f}")
    print(f"  Median = {np.median(arr):.2f}")

# ============================================================
# Supplementary: Shapiro-Wilk normality test
# ============================================================
print("\n" + "="*80)
print("SUPPLEMENTARY: Shapiro-Wilk normality test on paired differences")
print("="*80)
shapiro_stat, shapiro_p = stats.shapiro(diff)
print(f"  W = {shapiro_stat:.4f}, p = {shapiro_p:.4f}")
if shapiro_p < 0.05:
    print("  Interpretation: Differences are NOT normally distributed (p < 0.05)")
    print("  => Wilcoxon test is the more appropriate primary test")
else:
    print("  Interpretation: No evidence against normality (p >= 0.05)")
    print("  => Both parametric (t-test) and non-parametric (Wilcoxon) are valid")

# Effect size for Wilcoxon: rank-biserial correlation
print("\n" + "="*80)
print("SUPPLEMENTARY: Wilcoxon rank-biserial correlation (effect size for Wilcoxon)")
print("="*80)
n_pairs = len(diff[diff != 0])
r_rb = 1 - (2 * wilcoxon_result.statistic) / (n_pairs * (n_pairs + 1) / 2)
print(f"  r = {r_rb:.4f}")
if abs(r_rb) >= 0.5:
    print(f"  Interpretation: large effect")
elif abs(r_rb) >= 0.3:
    print(f"  Interpretation: medium effect")
elif abs(r_rb) >= 0.1:
    print(f"  Interpretation: small effect")
else:
    print(f"  Interpretation: negligible effect")

# ============================================================
# 7. LaTeX summary table
# ============================================================
print("\n" + "="*80)
print("7. LaTeX-READY SUMMARY TABLE")
print("="*80)

sel_rt = np.array(selected_runtime)
bld_rt = np.array(build_runtime)
cmp_rt = np.array(complete_runtime)

latex = r"""\begin{table}[htbp]
\centering
\caption{Statistical comparison of workflow strategies on norm coverage index ($n = """ + str(len(diff)) + r"""$ paired scenarios).}
\label{tab:statistical_tests}
\begin{tabular}{lrl}
\toprule
\textbf{Metric / Test} & \textbf{Value} & \textbf{Interpretation} \\
\midrule
\multicolumn{3}{l}{\textit{Descriptive statistics: norm\_coverage\_index}} \\
\quad \texttt{build\_from\_library} mean $\pm$ SD & $""" + f"{np.mean(build_cov):.2f} \\pm {np.std(build_cov, ddof=1):.2f}" + r"""$ & --- \\
\quad \texttt{complete\_from\_library} mean $\pm$ SD & $""" + f"{np.mean(complete_cov):.2f} \\pm {np.std(complete_cov, ddof=1):.2f}" + r"""$ & --- \\
\quad \texttt{selected\_only} mean $\pm$ SD & $""" + f"{np.mean(selected_cov):.2f} \\pm {np.std(selected_cov, ddof=1):.2f}" + r"""$ & --- \\
\quad Mean paired difference (complete $-$ build) & $""" + f"{mean_diff:.2f}" + r"""$ & --- \\
\midrule
\multicolumn{3}{l}{\textit{Inferential tests: complete\_from\_library vs.\ build\_from\_library}} \\
\quad Wilcoxon signed-rank $W$ & $""" + f"{wilcoxon_result.statistic:.1f}" + r"""$ & """ + sig_interp + r""" \\
\quad Wilcoxon $p$-value & $""" + f"{wilcoxon_result.pvalue:.4f}" + r"""$ & \\
\quad Paired $t$-test $t(""" + str(len(diff)-1) + r""")$ & $""" + f"{ttest_result.statistic:.4f}" + r"""$ & """ + sig_interp_t + r""" \\
\quad Paired $t$-test $p$-value & $""" + f"{ttest_result.pvalue:.4f}" + r"""$ & \\
\quad 95\% CI of mean difference & $[""" + f"{ci_low:.2f},\\ {ci_high:.2f}" + r"""]$ & \\
\quad Cohen's $d$ (paired) & $""" + f"{d:.4f}" + r"""$ & """ + d_interp + r""" effect \\
\quad Bootstrap 95\% CI ($B = 10{,}000$) & $[""" + f"{boot_ci_low:.2f},\\ {boot_ci_high:.2f}" + r"""]$ & \\
\midrule
\multicolumn{3}{l}{\textit{Sign test}} \\
\quad Scenarios where complete $>$ build & $""" + f"{n_positive}" + r"""/""" + f"{len(diff)}" + r"""$ & """ + f"{n_positive/len(diff)*100:.1f}" + r"""\% \\
\quad Sign test $p$-value & $""" + f"{sign_test.pvalue:.4f}" + r"""$ & \\
\midrule
\multicolumn{3}{l}{\textit{Runtime (ms), across-scenario}} \\
\quad \texttt{selected\_only}: median [IQR] & $""" + f"{np.median(sel_rt):.2f}" + r"""\ [""" + f"{np.percentile(sel_rt, 25):.2f}" + r"""$--$""" + f"{np.percentile(sel_rt, 75):.2f}" + r"""]$ & \\
\quad \texttt{build\_from\_library}: median [IQR] & $""" + f"{np.median(bld_rt):.2f}" + r"""\ [""" + f"{np.percentile(bld_rt, 25):.2f}" + r"""$--$""" + f"{np.percentile(bld_rt, 75):.2f}" + r"""]$ & \\
\quad \texttt{complete\_from\_library}: median [IQR] & $""" + f"{np.median(cmp_rt):.2f}" + r"""\ [""" + f"{np.percentile(cmp_rt, 25):.2f}" + r"""$--$""" + f"{np.percentile(cmp_rt, 75):.2f}" + r"""]$ & \\
\midrule
\multicolumn{3}{l}{\textit{Normality check (Shapiro--Wilk on differences)}} \\
\quad $W$ & $""" + f"{shapiro_stat:.4f}" + r"""$ & $p = """ + f"{shapiro_p:.4f}" + r"""$ \\
\bottomrule
\end{tabular}
\end{table}"""

print(latex)

# Print all individual paired differences for transparency
print("\n" + "="*80)
print("APPENDIX: Individual case-level paired differences (complete - build)")
print("="*80)
for i, case in enumerate(cases):
    case_id = case["case"]["id"]
    print(f"  {i+1:2d}. {case_id:40s}  build={build_cov[i]:.2f}  complete={complete_cov[i]:.2f}  diff={diff[i]:+.2f}")
