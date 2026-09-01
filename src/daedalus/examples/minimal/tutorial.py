# %% [markdown]
# # Your first daedalus Lab

# daedalus runs small analysis pipelines. A Lab is a short recipe that lists the
# modules to run. daedalus works out the order, runs each one, and files every
# result in a timestamped folder, so each output traces back to its run.

# This Lab is the smallest one possible, a single module. The cells below
# scaffold it, look inside it, run it, and show where the result landed. Each
# cell is a real command; run them in order with Shift+Enter.

# %% [markdown]
# Setup. This notebook writes files, so it starts in a fresh scratch folder and
# stays repeatable. In a shell, `cd` to where the Lab should live instead.

# %%
import os
import tempfile

os.chdir(tempfile.mkdtemp(prefix="dae-tutorial-minimal-"))

# %% [markdown]
# ## 1. Start from a ready-made example

# `dae example` ships small Labs to start from. Scaffold the `minimal` one into
# a new folder:

# %%
# !dae example minimal

# %% [markdown]
# That created a `minimal/` folder with three things.

# - `lab.yaml`, the recipe: which modules to run and how they depend on each other.
# - `modules/normalize/`, the single module, an ordinary Python file.
# - `input/`, the folder daedalus hands to the first module to read.

# Move into the new folder so the next commands act on this Lab:

# %%
# %cd minimal

# %% [markdown]
# ## 2. Look inside a module

# A module is a Python function with one argument, `ctx`. daedalus fills it with
# the input and output folders for that run; the code builds no path by hand.
# Each run of a module is a step, hence the `step_` prefix.

# The module reads from `ctx.step_input_path` and writes to `ctx.step_output_path`.
# For the first module the input folder is this Lab's `input/`, which holds the
# raw light curve as `raw.csv`. Here is the whole module:

# %%
# !cat modules/normalize/main.py

# %% [markdown]
# ## 3. Check the recipe

# `dae lab validate` reads `lab.yaml` and checks that every module it names
# exists and that the dependencies form a valid order with no loops.

# %%
# !dae lab validate

# %% [markdown]
# ## 4. Run the Lab

# `dae lab run` creates a fresh, timestamped folder under `dae-outputs/`, runs
# `normalize`, and saves its output there. That folder is the run's lineage, a
# permanent, dated record of what the run produced.

# %%
# !dae lab run

# %% [markdown]
# ## 5. See what happened

# `dae flow status` reports on the most recent run, which modules ran and where
# their outputs were written.

# %%
# !dae flow status

# %% [markdown]
# ## Next

# Describe modules, run, inspect: that is the whole daedalus loop. The demo
# notebook shows the full picture, many targets in parallel, two methods
# compared, and the results combined.
