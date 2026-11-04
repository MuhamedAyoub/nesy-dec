"""Neural analysis layer for Paper 2.

Modules:
  model    — UnixCoder + LoRA wrapper, embedding extraction
  dataset  — TripletDataset that joins triplets.json with code_index.json
  loss     — triplet loss + symbolic-constraint regularizer
  train    — training loop entry point
"""
