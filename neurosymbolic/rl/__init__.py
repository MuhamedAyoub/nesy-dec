"""Phase 3 — graph-RL decomposition.

Pipeline:
  rails-aware coupling graph + UnixCoder embeddings (Phase 1)
    -> GNN encoder (GraphSAGE)
    -> PPO agent assigns each class to a cluster
    -> reward = Weerasinghe Eq.5 Score against the existing MVC partition's
       dependency graph
    -> hard masking via must_link / cannot_link from neurosymbolic/symbolic/

This subpackage is intentionally self-contained: graph_env owns the MDP,
policy owns the network, train owns the optimizer loop, decompose owns
inference + persisting the partition in the same exp_*.json shape the rest
of the repo consumes.
"""

from .graph_env import RailsDecompositionEnv, EnvConfig  # noqa: F401
from .policy import GNNActorCritic, PolicyConfig  # noqa: F401
