import annpy
from annpy.losses.Loss import Loss
from annpy.layers.Layer import Layer
from annpy.metrics.Metric import Metric
from annpy.metrics.Accuracy import Accuracy
from annpy.metrics.RangeAccuracy import RangeAccuracy
from annpy.optimizers.Optimizer import Optimizer

import json
import numpy as np
import pandas as pd
import plotly.express as px

class SequencialModel():

	@classmethod
	def shuffle_datasets(cls, a, b, copy=False):

		if copy:
			a = a.copy()
			b = b.copy()

		seed = np.random.get_state()
		np.random.shuffle(a)
		np.random.set_state(seed)
		np.random.shuffle(b)
		return a, b

	@classmethod
	def train_test_split(cls, features, targets, val_percent, shuffle=True):

		if shuffle:
			features, targets = cls.shuffle_datasets(features, targets)

		i = int(val_percent * len(features))
		return features[i:, :], targets[i:, :], features[:i, :], targets[:i, :]

	name: str
	input_shape: int

	weightsB:		list = []	# list of layers: [[w0, b0], [..., ...], [wn, bn]]
	sequence:		list = []	# list of Object: [L0, ..., Ln]
	sequence_rev:	list = []	# list of Object: [L0, ..., Ln]

	train_features:		np.ndarray
	train_targets:		np.ndarray
	val_features:		np.ndarray
	val_targets:		np.ndarray
	last_batch_size:	int		# last full batch size index

	loss:		Loss = None
	optimizer:	Optimizer = None
	accuracy:	Metric = None

	metrics:		dict = {}	# All metrics used for all fitting (train & validation)

	stop_trainning:	bool = False
	val_on:			bool = True

	save_weights_method: str = "Only weights"

	def __init__(self,
					input_shape=None,
					input_layer=None,
					name="default_model_name",
					seed=None):

		if seed:
			self.seed = seed
			np.random.set_state(seed)
		else:
			self.seed = np.random.get_state() ###########################################

		self.name = name
		self.input_shape = input_shape
		self.weightsB = []

		if input_layer:
			self.sequence = [input_layer]
		else:
			self.sequence = []

		self.metrics = {}
		self.loss = None
		self.optimizer = None
		self.accuracy = None

		self.stop_trainning = False
		self.val_on = True

	def __str__(self):
		return "SequentialModel"

	def add(self, layer):

		if issubclass(type(layer), Layer):
			# Add Object into sequential model
			layer.set_layer_index(len(self.sequence))
			self.sequence.append(layer)

		else:
			raise Exception(f"[annpy error]:Object {layer} is not a child of abstact class {Layer}")

	def add_metric(self, metric):

		cpy = metric.copy().set_name('val_' + str(metric))
		self.metrics[str(cpy)] = cpy
		self.metrics[str(metric)] = metric

	def compile(self,
				loss="MSE",
				optimizer="Adam",
				metrics=[]):

		# -- MODEL --

		if not isinstance(metrics, list):
			raise TypeError("[annpy error] Model: Metrics parameter in compile() is not a list")

		# Parse optimizer, loss
		self.optimizer = annpy.utils.parse.parse_object(optimizer, Optimizer)
		self.loss = annpy.utils.parse.parse_object(loss, Loss)
		self.add_metric(self.loss)

		# Parse metrics
		for metric in metrics:
			self.add_metric(annpy.utils.parse.parse_object(metric, Metric))

		# print(self.metrics)
		# exit()

		# -- SEQUENCIAL --

		# Handling input_shape
		if self.input_shape:
			pass
		elif self.sequence[0].input_shape:
			self.input_shape = self.sequence[0].input_shape
			print(f"AVOUE TA JAMAIS VU CE PRINT ALORS EFFACE MOI")
		else:
			raise Exception(f"[annpy error] {self} input_shape of layer 0 missing")

		input_shape = self.input_shape
		for layer in self.sequence:

			# Compile all layers
			weightsB = layer.compile(input_shape)
			self.weightsB.append(weightsB)

			# Save weights reference in optimizer
			self.optimizer.add(weightsB)

			# Save next input shape
			input_shape = layer.output_shape

		# Compile optimizer
		self.optimizer.compile()

		# Make reverse list for fitting method
		self.sequence_rev = self.sequence.copy()
		self.sequence_rev.reverse()

	def get_seed(self):
		return self.seed

	def forward(self, inputs):
		for layer in self.sequence:
			inputs = layer.forward(inputs)
		return inputs

	def evaluate(self, model, features, target, metrics_on=True, return_stats=False):

		prediction = model.forward(features)

		# Metrics actualisation
		for metric in self.metrics.values():
			if 'val_' in str(metric):
				metric.reset(save=False)
				metric(prediction, target)

		if return_stats:
			return self.loss.get_result()


	def dataset_fit_setup(self, train_features, train_targets, val_features, val_targets, val_percent):

		if val_features and val_targets:
			# print(f"Validation dataset is past")
			datasets = train_features, train_targets, val_features, val_targets

		# Split train dataset in two parts
		elif val_percent:
			# print(f"Split datasets in 2 batch with val_percent={val_percent}")
			datasets = SequencialModel.train_test_split(train_features, train_targets, val_percent)

		else:
			# print(f"No validation dataset: train dataset is using for validation")
			datasets = train_features, train_targets, train_features, train_targets
			self.val_on = False

		self.train_features = datasets[0]
		self.train_targets = datasets[1]
		self.val_features = datasets[2]
		self.val_targets = datasets[3]

	def batchs_split(self, shuffle=True):

		a, b = self.train_features, self.train_targets

		# Shuffle
		if shuffle:
			a, b = SequencialModel.shuffle_datasets(self.train_features, self.train_targets, copy=False)

		if self.last_batch_size:
			last_f = a[-self.last_batch_size:]
			last_t = b[-self.last_batch_size:]

			a = a[:-self.last_batch_size]
			b = b[:-self.last_batch_size]

			# Split batches
			a = np.array_split(a, self.n_batch_full)
			b = np.array_split(b, self.n_batch_full)

			a.append(last_f)
			b.append(last_t)

		else:
			# Just Split batches
			a = np.array_split(a, self.n_batch_full)
			b = np.array_split(b, self.n_batch_full)

		# Merge
		return list(zip(a, b))

	def fit(self,
			train_features,
			train_targets,
			batch_size=42,
			epochs=420,
			callbacks=[],
			val_features=None,
			val_targets=None,
			val_percent=0.2,
			shuffle=True,
			verbose=True,
			print_graph=True):

		# Parse datasets
		self.dataset_fit_setup(train_features, train_targets, val_features, val_targets, val_percent)

		# Batchs stats
		self.last_batch_size = len(self.train_features) % batch_size
		self.n_batch_full = len(self.train_features) // batch_size
		self.n_batch = self.n_batch_full + 1 if self.last_batch_size else self.n_batch_full
		# print(f"batch_size: {batch_size}\tn_batch_full: {self.n_batch_full}\tlast_batch_size: {self.last_batch_size}")

		# Reset metrics for new model fit
		self.hard_reset_metrics()

		# Callbacks TRAIN begin
		for cb in callbacks:
			cb.on_train_begin(model=self)

		for epoch in range(epochs):

			if verbose:
				print(f"EPOCH {epoch}")

			# Callbacks EPOCH begin
			for cb in callbacks:
				cb.on_epoch_begin()

			# Dataset shuffle + split
			batchs = self.batchs_split(shuffle=shuffle)

			# for step, (features, target) in enumerate(batchs):
			for step, data in enumerate(batchs):

				if verbose:
					print(f"STEP={step}/{self.n_batch - 1}")
					# print(f"STEP={step}/{self.n_batch - 1}\tloss: {self.loss.get_result()}")

				# Callbacks BATCH begin
				for cb in callbacks:
					cb.on_batch_begin()

				features, target = data

				# Prediction
				prediction = self.forward(features)

				# Metrics actualisation
				for metric in self.metrics.values():
					if 'val_' not in str(metric):
						metric(prediction, target)

				# Backpropagation
				dx = self.loss.derivate(prediction, target)
				
				# For sequential model: dw, db
				gradients = [0, 0]
				
				self.optimizer.gradients = []
				for layer in self.sequence_rev:
					# print(f"LAYER {layer.layer_index}")
					dx, gradients = layer.backward(dx)
					# gradients = layer.backward(gradients[0])
					self.optimizer.gradients.append(gradients)

				# Optimizer
				self.optimizer.apply_gradients(self.weightsB)

				# Callbacks BATCH end
				for cb in callbacks:
					cb.on_batch_end()

			self.evaluate(self, self.val_features, self.val_targets)

			if verbose:
				# Get total metrics data of this epoch
				print(f"Metrics: {self.get_metrics_logs()}")
				print(f"\n-------------------------\n")

			# Callbacks EPOCH end
			for cb in callbacks:
				cb.on_epoch_end(verbose=verbose)

			# Save in mem & Reset metrics values
			self.reset_metrics(save=True)

			if self.stop_trainning:
				break

		if print_graph:
			self.print_graph()

		# Callbacks TRAIN end
		for cb in callbacks:
			cb.on_train_end()

		return {
			"loss": self.loss.get_mem()[-1]
		}


	def get_metrics_logs(self):
		return ''.join(metric.log() for metric in self.metrics.values())

	def reset_metrics(self, save=False):
		for metric in self.metrics.values():
			metric.reset(save)

	def hard_reset_metrics(self):
		# print(f"Metrics:\n{self.metrics}")
		for metric in self.metrics.values():
			metric.hard_reset()

	def print_graph(self, metrics=[]):

		if metrics:
			metrics = [self.metrics[metric_name] for metric_name in metrics]
		else:
			metrics = self.metrics.values()

		data = {}
		for metric in metrics:
			data[str(metric)] = metric.get_mem()

		data = {k:v for k, v in data.items() if len(v)}
		data['Subject goal'] = [0.08] * len(list(data.values())[0])
		data_df = pd.DataFrame(data)

		best_val = {key: max(values) if "accuracy" in key.lower() else min(values) for key, values in data.items()}

		print(data_df)
		print(f"Best metrics value: {best_val}")

		fig = px.line(data_df)
		fig.show()

	def _save(self):
		return {
			"type": "SequentialModel",
			"name": self.name,
			"layers": [layer._save() for layer in self.sequence]
		}

	def save_weights(self, folder_path):

		struct = {
			"file": self.save_weights_method,
			"model": self._save()
		}

		print(struct)
		with open(f"{folder_path}/{self.name}_weights.json", 'w') as f:
			# f.write(struct)
			json.dump(struct, f, indent=4)

		return struct

	def summary(self, only_model_summary=True):

		print(f"Input shape:\t{self.input_shape}")
		print(f"Output shape:\t{self.sequence[-1].output_shape}\n")
		for layer in self.sequence:
			layer.summary()

		if only_model_summary:
			print(f"-------------------\n")

	def deepsummary(self, model_summary=True):
		
		if model_summary:
			self.summary(only_model_summary=False)

		for i, layer in enumerate(self.weightsB):
			print(f"\nLayer {i}:\n")
			print(f"Weights {layer[0].shape}:\n{layer[0]}\n")
			print(f"Bias {layer[1].shape}:\n{layer[1]}\n")

		print(f"-------------------\n")
