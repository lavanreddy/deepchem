"""TensorFlow implementation of the models from the ICML-2015 paper.


hyperparam_dict = {
    "single": Hyperparams(num_layers=1,
                          num_hidden=1200,
                          node_depth=1,
                          nonlinearity=ACTIVATION_RECTIFIED_LINEAR,
                          weight_init=GaussianWeightInit(0.01),
                          bias_init=ConstantBiasInit(0.5),
                          dropout=1.),
    "deep": Hyperparams(num_layers=4,
                        num_hidden=1000,
                        node_depth=1,
                        nonlinearity=ACTIVATION_RECTIFIED_LINEAR,
                        weight_init=GaussianWeightInit(0.01),
                        bias_init=ConstantBiasInit(0.5),
                        dropout=1.),
    "deepaux": Hyperparams(num_layers=4,
                        num_hidden=1000,
                        auxiliary_softmax_layers=[0, 1, 2],
                        auxiliary_softmax_weight=0.3,
                        node_depth=1,
                        nonlinearity=ACTIVATION_RECTIFIED_LINEAR,
                        weight_init=GaussianWeightInit(0.01),
                        bias_init=ConstantBiasInit(0.5),
                        dropout=1.),
    "py": Hyperparams(num_layers=2,
                      num_hidden=[2000, 100],
                      node_depth=1,
                      nonlinearity=ACTIVATION_RECTIFIED_LINEAR,
                      weight_init=[GaussianWeightInit(0.01),
                                   GaussianWeightInit(0.04)],
                      bias_init=[ConstantBiasInit(0.5),
                                 ConstantBiasInit(3.0)],
                      dropout=1.),
    "pydrop1": Hyperparams(num_layers=2,
                           num_hidden=[2000, 100],
                           node_depth=1,
                           nonlinearity=ACTIVATION_RECTIFIED_LINEAR,
                           weight_init=[GaussianWeightInit(0.01),
                                        GaussianWeightInit(0.04)],
                           bias_init=[ConstantBiasInit(0.5),
                                      ConstantBiasInit(3.0)],
                           dropout=[0.75, 1.]),
    "pydrop2": Hyperparams(num_layers=2,
                           num_hidden=[2000, 100],
                           node_depth=1,
                           nonlinearity=ACTIVATION_RECTIFIED_LINEAR,
                           weight_init=[GaussianWeightInit(0.01),
                                        GaussianWeightInit(0.04)],
                           bias_init=[ConstantBiasInit(0.5),
                                      ConstantBiasInit(3.0)],
                           dropout=[0.75, 0.75])}
"""
from __future__ import print_function
from __future__ import division
from __future__ import unicode_literals

import time
import numpy as np
import tensorflow as tf
from tensorflow.python.platform import logging

from deepchem.models.tensorflow_models import TensorflowClassifier
from deepchem.models.tensorflow_models import TensorflowRegressor
from deepchem.models.tensorflow_models import model_ops
from deepchem.metrics import to_one_hot

class TensorflowMultiTaskClassifier(TensorflowClassifier):
  """Implements an icml model as configured in a model_config.proto."""

  def build(self):
    """Constructs the graph architecture as specified in its config.

    This method creates the following Placeholders:
      mol_features: Molecule descriptor (e.g. fingerprint) tensor with shape
        batch_size x num_features.
    """
    assert len(self.model_params["data_shape"]) == 1
    num_features = self.model_params["data_shape"][0]
    with self.graph.as_default():
      with tf.name_scope(self.placeholder_scope):
        self.mol_features = tf.placeholder(
            tf.float32,
            shape=[self.model_params["batch_size"],
                   num_features],
            name='mol_features')

      layer_sizes = self.model_params["layer_sizes"]
      weight_init_stddevs = self.model_params["weight_init_stddevs"]
      bias_init_consts = self.model_params["bias_init_consts"]
      dropouts = self.model_params["dropouts"]
      lengths_set = {
          len(layer_sizes),
          len(weight_init_stddevs),
          len(bias_init_consts),
          len(dropouts),
          }
      assert len(lengths_set) == 1, 'All layer params must have same length.'
      num_layers = lengths_set.pop()
      assert num_layers > 0, 'Must have some layers defined.'

      prev_layer = self.mol_features
      prev_layer_size = num_features 
      for i in xrange(num_layers):
        layer = tf.nn.relu(model_ops.FullyConnectedLayer(
            tensor=prev_layer,
            size=layer_sizes[i],
            weight_init=tf.truncated_normal(
                shape=[prev_layer_size, layer_sizes[i]],
                stddev=weight_init_stddevs[i]),
            bias_init=tf.constant(value=bias_init_consts[i],
                                  shape=[layer_sizes[i]])))
        layer = model_ops.Dropout(layer, dropouts[i])
        prev_layer = layer
        prev_layer_size = layer_sizes[i]

      self.output = model_ops.MultitaskLogits(
          layer, self.model_params["num_classification_tasks"])

  def construct_feed_dict(self, X_b, y_b=None, w_b=None, ids_b=None):
    """Construct a feed dictionary from minibatch data.

    TODO(rbharath): ids_b is not used here. Can we remove it?

    Args:
      X_b: np.ndarray of shape (batch_size, num_features)
      y_b: np.ndarray of shape (batch_size, num_tasks)
      w_b: np.ndarray of shape (batch_size, num_tasks)
      ids_b: List of length (batch_size) with datapoint identifiers.
    """ 
    orig_dict = {}
    orig_dict["mol_features"] = X_b
    for task in xrange(self.num_tasks):
      if y_b is not None:
        orig_dict["labels_%d" % task] = to_one_hot(y_b[:, task])
      else:
        # Dummy placeholders
        orig_dict["labels_%d" % task] = np.squeeze(to_one_hot(
            np.zeros((self.model_params["batch_size"],))))
      if w_b is not None:
        orig_dict["weights_%d" % task] = w_b[:, task]
      else:
        # Dummy placeholders
        orig_dict["weights_%d" % task] = np.ones(
            (self.model_params["batch_size"],)) 
    orig_dict["valid"] = np.ones((self.model_params["batch_size"],), dtype=bool)
    return self._get_feed_dict(orig_dict)

class TensorflowMultiTaskRegressor(TensorflowRegressor):
  """Implements an icml model as configured in a model_config.proto."""

  def build(self):
    """Constructs the graph architecture as specified in its config.

    This method creates the following Placeholders:
      mol_features: Molecule descriptor (e.g. fingerprint) tensor with shape
        batch_size x num_features.
    """
    assert len(self.model_params["data_shape"]) == 1
    num_features = self.model_params["data_shape"][0]
    with self.graph.as_default():
      with tf.name_scope(self.placeholder_scope):
        self.mol_features = tf.placeholder(
            tf.float32,
            shape=[self.model_params["batch_size"],
                   num_features],
            name='mol_features')

      layer_sizes = self.model_params["layer_sizes"]
      weight_init_stddevs = self.model_params["weight_init_stddevs"]
      bias_init_consts = self.model_params["bias_init_consts"]
      dropouts = self.model_params["dropouts"]
      lengths_set = {
          len(layer_sizes),
          len(weight_init_stddevs),
          len(bias_init_consts),
          len(dropouts),
          }
      assert len(lengths_set) == 1, 'All layer params must have same length.'
      num_layers = lengths_set.pop()
      assert num_layers > 0, 'Must have some layers defined.'

      prev_layer = self.mol_features
      prev_layer_size = num_features 
      for i in xrange(num_layers):
        layer = tf.nn.relu(model_ops.FullyConnectedLayer(
            tensor=prev_layer,
            size=layer_sizes[i],
            weight_init=tf.truncated_normal(
                shape=[prev_layer_size, layer_sizes[i]],
                stddev=weight_init_stddevs[i]),
            bias_init=tf.constant(value=bias_init_consts[i],
                                  shape=[layer_sizes[i]])))
        layer = model_ops.Dropout(layer, dropouts[i])
        prev_layer = layer
        prev_layer_size = layer_sizes[i]

      self.output = [tf.squeeze(model_ops.FullyConnectedLayer(
          tensor=prev_layer,
          size=layer_sizes[i],
          weight_init=tf.truncated_normal(
              shape=[prev_layer_size, 1],
              stddev=weight_init_stddevs[i]),
          bias_init=tf.constant(value=bias_init_consts[i],
                                shape=[1])))]

  def construct_feed_dict(self, X_b, y_b=None, w_b=None, ids_b=None):
    """Construct a feed dictionary from minibatch data.

    TODO(rbharath): ids_b is not used here. Can we remove it?

    Args:
      X_b: np.ndarray of shape (batch_size, num_features)
      y_b: np.ndarray of shape (batch_size, num_tasks)
      w_b: np.ndarray of shape (batch_size, num_tasks)
      ids_b: List of length (batch_size) with datapoint identifiers.
    """ 
    orig_dict = {}
    orig_dict["mol_features"] = X_b
    for task in xrange(self.num_tasks):
      if y_b is not None:
        orig_dict["labels_%d" % task] = y_b[:, task]
      else:
        # Dummy placeholders
        orig_dict["labels_%d" % task] = np.squeeze(
            np.zeros((self.model_params["batch_size"],)))
      if w_b is not None:
        orig_dict["weights_%d" % task] = w_b[:, task]
      else:
        # Dummy placeholders
        orig_dict["weights_%d" % task] = np.ones(
            (self.model_params["batch_size"],)) 
    orig_dict["valid"] = np.ones((self.model_params["batch_size"],), dtype=bool)
    return self._get_feed_dict(orig_dict)

  def predict_on_batch(self, X):
    """Return model output for the provided input.

    Restore(checkpoint) must have previously been called on this object.

    Args:
      dataset: deepchem.datasets.dataset object.

    Returns:
      Tuple of three numpy arrays with shape num_examples x num_tasks (x ...):
        output: Model outputs.
        labels: True labels.
        weights: Example weights.
      Note that the output and labels arrays may be more than 2D, e.g. for
      classifier models that return class probabilities.

    Raises:
      AssertionError: If model is not in evaluation mode.
      ValueError: If output and labels are not both 3D or both 2D.
    """
    if not self._restored_model:
      self.restore()
    with self.graph.as_default():
      assert not model_ops.is_training()
      self.require_attributes(['output', 'labels', 'weights'])

      # run eval data through the model
      num_tasks = self.num_tasks
      output, labels, weights = [], [], []
      start = time.time()
      with self._get_shared_session().as_default():
        batch_count = -1.0

        feed_dict = self.construct_feed_dict(X)
        batch_start = time.time()
        batch_count += 1
        data = self._get_shared_session().run(
            self.output + self.labels + self.weights,
            feed_dict=feed_dict)
        batch_output = np.asarray(data[:num_tasks], dtype=float)
        batch_labels = np.asarray(data[num_tasks:num_tasks * 2], dtype=float)
        batch_weights = np.asarray(data[num_tasks * 2:num_tasks * 3],
                                   dtype=float)
        # reshape to batch_size x num_tasks x ...
        if batch_output.ndim == 3 and batch_labels.ndim == 3:
          batch_output = batch_output.transpose((1, 0, 2))
          batch_labels = batch_labels.transpose((1, 0, 2))
        elif batch_output.ndim == 2 and batch_labels.ndim == 2:
          batch_output = batch_output.transpose((1, 0))
          batch_labels = batch_labels.transpose((1, 0))
        else:
          raise ValueError(
              'Unrecognized rank combination for output and labels: %s %s' %
              (batch_output.shape, batch_labels.shape))
        batch_weights = batch_weights.transpose((1, 0))
        valid = feed_dict[self.valid.name]
        # only take valid outputs
        if np.count_nonzero(~valid):
          batch_output = batch_output[valid]
          batch_labels = batch_labels[valid]
          batch_weights = batch_weights[valid]
        output.append(batch_output)
        labels.append(batch_labels)
        weights.append(batch_weights)

        logging.info('Eval batch took %g seconds', time.time() - start)

        #labels = np.array(from_one_hot(
        #    np.squeeze(np.concatenate(labels)), axis=-1))
        labels = np.squeeze(np.concatenate(labels)) 

    return np.copy(labels)

