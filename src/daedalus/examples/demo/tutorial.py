# %% [markdown]
# # The demo Lab, two ways to fit a transit

# The minimal notebook shows the daedalus loop on one module. This Lab is the
# full picture. It takes three exoplanets, fits each transit light curve two
# different ways, and measures how much the two methods disagree.

# That spread comes from the choice of method, not from the data, and is a
# method-driven uncertainty. Along the way the Lab uses all four kinds of
# daedalus module.

# %% [markdown]
# ## How the Lab is shaped

# A module is a definition, one folder under `modules/`. Each run of a module is
# a step, so one module can become many steps in a run. A module runs more than
# once in two ways.

# - A Flight is one pass through the Lab for one target: three targets, three Flights.
# - A Walk is one method branch within a Flight: two methods, two Walks per Flight.

# The recipe runs top to bottom. `emit_targets` declares one Flight per target.
# `fetch_data` gets each target's light curve; the run splits into Walks there.
# `fit_nested` and `fit_mcmc` are the two Walks, one per method.

# `compare_methods` joins the two Walks of a target; `summarize_population` joins
# all three targets.

# Each module has a role that tells daedalus how it behaves. `emit_targets` is an
# emitter, the middle modules are transforms (one in, one out), `compare_methods`
# is a walk-collector, and `summarize_population` is a flight-collector.

# %% [markdown]
# Setup. This notebook writes files, so it starts in a fresh scratch folder and
# stays repeatable. In a shell, `cd` to where the Lab should live instead.

# %%
import os
import tempfile

os.chdir(tempfile.mkdtemp(prefix="dae-tutorial-demo-"))

# %% [markdown]
# ## 1. Scaffold the Lab and move into it

# %%
# !dae example demo

# %%
# %cd demo

# %% [markdown]
# ## 2. See the recipe

# `dae lab visualize` draws the modules, how they feed into each other, and each
# module's role.

# %%
# !dae lab visualize

# %% [markdown]
# The diagram shows the recipe, each module once. `fetch_data` feeds both fits, so
# each target's run splits into two Walks there; `compare_methods` rejoins them.

# %% [markdown]
# ## 3. Check it holds together

# %%
# !dae lab validate

# %% [markdown]
# ## 4. Run the Lab

# When it runs, daedalus expands the recipe over the data. Three targets, each
# fit two ways, comes to 14 step runs: `emit_targets` once, four modules for
# each of the three targets, and `summarize_population` once at the end.

# Every result is filed by Flight and Walk under `dae-outputs/flows/<flow>/`, so
# any number traces back to the target and method that produced it.

# %%
# !dae lab run

# %% [markdown]
# ## 5. Inspect the run

# `dae flow status` shows each step, whether it finished, and where its output
# landed, per target and per method.

# %%
# !dae flow status

# %% [markdown]
# ## What the result tells you

# For each target, `compare_methods` writes the Wasserstein and Hellinger
# distances between the two depth posteriors, plus the absolute gap between the
# two depth estimates.

# A clean, bright target is fit almost the same way by both methods; a faint,
# low-signal one is not. That gap is the method-driven uncertainty, and
# `summarize_population` reports its average across all three targets.

# ## Next

# To start an analysis of your own, run `dae lab init your-project` and build a
# Lab from the same pieces.
