# coding=utf-8
# Copyright 2019 The Trax Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Trax metrics layers."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import jax

from trax import math
from trax.layers import base
from trax.layers import combinators as cb
from trax.layers import core
from trax.math import numpy as np


@base.layer(n_in=2, n_out=1)
def CrossEntropy(inputs, axis=-1, **unused_kwargs):
  prediction, target = inputs
  return np.sum(prediction * one_hot(target, prediction.shape[-1]), axis=axis)


@base.layer(n_in=2, n_out=1)
def L2(inputs, axis=-1, **unused_kwargs):
  prediction, target = inputs
  return np.sum((prediction - target)**2, axis=axis)


@base.layer(n_in=2, n_out=1)
def Accuracy(inputs, axis=-1, **unused_kwargs):
  prediction, target = inputs
  predicted_class = np.argmax(prediction, axis=axis)
  return np.equal(predicted_class, target)


@base.layer()
def WeightMask(target, mask_id=0, **unused_kwargs):
  if mask_id is None:
    return np.ones_like(target)
  return 1.0 - np.equal(target, mask_id).astype(np.float32)


@base.layer(n_in=2, n_out=1)
def WeightedMean(inputs, **unused_kwargs):
  metric, weights = inputs
  weights_sum = np.sum(weights)
  return np.sum(metric * weights) / weights_sum


def CountWeights(mask_id=None, has_weights=False):
  """Sum the weights assigned to all elements."""
  if has_weights:
    return cb.Serial(
        cb.Drop(),  # Drop inputs.
        WeightMask(mask_id=mask_id),  # pylint: disable=no-value-for-parameter
        cb.Multiply(),  # Multiply with provided mask.
        core.Sum(axis=None)  # Sum all weights.
    )
  return cb.Serial(
      cb.Drop(),  # Drop inputs.
      WeightMask(mask_id=mask_id),  # pylint: disable=no-value-for-parameter
      core.Sum(axis=None)  # Sum all weights.
  )


def MaskedScalar(metric_layer, mask_id=None, has_weights=False):
  """Metric as scalar compatible with Trax masking."""
  # Stack of (inputs, targets) --> (metric, weight-mask).
  metric_and_mask = [
      cb.Parallel(
          [],
          cb.Dup()  # Duplicate targets
      ),
      cb.Parallel(
          metric_layer,  # Metric: (inputs, targets) --> metric
          WeightMask(mask_id=mask_id)  # pylint: disable=no-value-for-parameter
      )
  ]
  if not has_weights:
    # Take (metric, weight-mask) and return the weighted mean.
    return cb.Serial(metric_and_mask, WeightedMean())  # pylint: disable=no-value-for-parameter
  return cb.Serial(
      metric_and_mask,
      cb.Parallel(
          [],
          cb.Multiply()  # Multiply given weights by mask_id weights
      ),
      WeightedMean()  # pylint: disable=no-value-for-parameter
  )


def CrossEntropyScalar(mask_id=None, has_weights=False):
  """Cross-entropy as scalar compatible with Trax masking."""
  return MaskedScalar(CrossEntropy(), mask_id=mask_id, has_weights=has_weights)  # pylint: disable=no-value-for-parameter


NegLogPerplexityScalar = CrossEntropyScalar


def CrossEntropyLossScalar(mask_id=None, has_weights=False):
  """Cross-entropy loss as scalar compatible with Trax masking."""
  return cb.Serial(
      CrossEntropyScalar(mask_id=mask_id, has_weights=has_weights),
      base.Fn(lambda x: x * -1.0),
  )


def L2Scalar(mask_id=None, has_weights=False):
  """L2 as scalar compatible with Trax masking."""
  return MaskedScalar(L2(), mask_id=mask_id, has_weights=has_weights)  # pylint: disable=no-value-for-parameter


def L2LossScalar(mask_id=None, has_weights=False):
  """L2 loss as scalar compatible with Trax masking."""
  return L2Scalar(mask_id=mask_id, has_weights=has_weights)


def AccuracyScalar(mask_id=None, has_weights=False):
  """Accuracy as scalar compatible with Trax masking."""
  return MaskedScalar(Accuracy(), mask_id=mask_id, has_weights=has_weights)  # pylint: disable=no-value-for-parameter


def one_hot(x, n_categories, dtype=np.float32):  # pylint: disable=invalid-name
  """Makes a one-hot array (n+1 dims) from an int-categorical array (n dims)."""
  indices_less_than_n = np.arange(n_categories)
  if math.backend_name() == 'jax':
    # Work around a jax broadcasting issue.
    indices_less_than_n = jax.lax.tie_in(x, indices_less_than_n)
  return np.array(x[..., np.newaxis] == indices_less_than_n, dtype)
