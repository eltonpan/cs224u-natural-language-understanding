import numpy as np
from np_model_base import NNModelBase
import utils

__author__ = "Christopher Potts"
__version__ = "CS224u, Stanford, Spring 2022"


class TreeNN(NNModelBase):
    def __init__(self, vocab, embedding=None, embed_dim=50, **kwargs):
        self.vocab = vocab
        self.vocab_lookup = dict(zip(self.vocab, range(len(self.vocab))))
        if embedding is None:
            embedding = self._define_embedding_matrix(
                len(self.vocab), embed_dim)
        self.embedding = embedding
        self._embed_dim = self.embedding.shape[1]
        super().__init__(**kwargs)
        self.hidden_dim = self.embed_dim * 2
        self.params += ['embedding', 'embed_dim']


    @property
    def embed_dim(self):
        return self._embed_dim

    @embed_dim.setter
    def embed_dim(self, value):
        self._embed_dim = value
        self.embedding = self._define_embedding_matrix(
            len(self.vocab), value)

    def initialize_parameters(self):
        # Hidden parameters for semantic composition:
        self.W = self.weight_init(self.hidden_dim, self.embed_dim)
        self.b = np.zeros(self.embed_dim)
        # Output classifier:
        self.W_hy = self.weight_init(self.embed_dim, self.output_dim)
        self.b_y = np.zeros(self.output_dim)

    def forward_propagation(self, subtree):
        """
        Forward propagation through the tree and through the
        softmax prediction layer on top. For each subtree

        [parent left right]

        we compute

        p = tanh([x_l; x_r]W + b)

        where x_l and x_r are the representations on the root of
        left and right, and [x_l; x_r] is their concatenation.

        The representation on the root is then fed to a softmax
        classifier.

        Returns
        ----------
        vectree : np.array or tuple of tuples (of tuples ...) of np.array
            Predicted vector representation of the entire tree
        y : np.array
            The predictions made for this example, dimension
            `self.output_dim`.

        """
        vectree = self._interpret(subtree)
        root = self._get_vector_tree_root(vectree)
        y = utils.softmax(root.dot(self.W_hy) + self.b_y)
        return vectree, y

    def _interpret(self, subtree):
        """
        The forward propagation through the tree itself (excluding
        the softmax prediction layer on top of this).

        Given an NLTK Tree instance `subtree`, this returns a vector
        if `subtree` is just a leaf node, else a tuple of tuples (of
        tuples ...) of vectors with the same shape as `subtree`,
        with each node now represented by vector.

        Parameters
        ----------
        subtree : nltk.tree.Tree

        Returns
        -------
        np.array or tuple-based representation of `subtree`.

        """
        # For NLTK `Tree` objects, this identifies leaf nodes:
        if isinstance(subtree, str):
            return self.get_word_rep(subtree)
        elif len(subtree) == 1:
            return self._interpret(subtree[0])
        else:
            left_subtree, right_subtree = subtree[0], subtree[1]
            # Recursive interpretation of the child trees:
            left_vectree = self._interpret(left_subtree)
            right_vectree = self._interpret(right_subtree)
            # Top representations of each child tree:
            left_rep = self._get_vector_tree_root(left_vectree)
            right_rep = self._get_vector_tree_root(right_vectree)
            # Concatenate and create the hidden representation:
            combined = np.concatenate((left_rep, right_rep))
            root_rep = self.hidden_activation(combined.dot(self.W) + self.b)
            # Return the full subtree of vectors:
            return (root_rep, left_vectree, right_vectree)

    @staticmethod
    def _get_vector_tree_root(vectree):
        """
        Returns `tree` if it represents only a lexical item, else
        the root (first member) of `tree`.

        Parameters
        ----------
        vectree : np.array or tuple of tuples (of tuples ...) of np.array

        Returns
        -------
        np.array

        """
        if isinstance(vectree, tuple):
            return vectree[0]
        else:
            return vectree

    def backward_propagation(self, vectree, predictions, ex, labels):
        root = self._get_vector_tree_root(vectree)
        # Output errors:
        y_err = predictions.copy()
        y_err[np.argmax(labels)] -= 1.0
        d_W_hy = np.outer(root, y_err)
        d_b_y = y_err
        # Internal error accumulation:
        d_W = np.zeros_like(self.W)
        d_b = np.zeros_like(self.b)
        h_err = y_err.dot(self.W_hy.T) * self.d_hidden_activation(root)
        d_W, d_b = self._tree_backprop(vectree, h_err, d_W, d_b)
        return d_W_hy, d_b_y, d_W, d_b

    def _tree_backprop(self, deep_tree, h_err, d_W, d_b):
        # This is the leaf-node condition for vector trees:
        if isinstance(deep_tree, np.ndarray):
            return d_W, d_b
        else:
            left_subtree, right_subtree = deep_tree[1], deep_tree[2]
            left_rep = self._get_vector_tree_root(left_subtree)
            right_rep = self._get_vector_tree_root(right_subtree)
            combined = np.concatenate((left_rep, right_rep))
            d_b += h_err
            d_W += np.outer(combined, h_err)
            err = h_err.dot(self.W.T) * self.d_hidden_activation(combined)
            l_err = err[: self.embed_dim]
            r_err = err[self.embed_dim: ]
            d_W, d_b = self._tree_backprop(left_subtree, l_err, d_W, d_b)
            d_W, d_b = self._tree_backprop(right_subtree, r_err, d_W, d_b)
            return d_W, d_b

    def update_parameters(self, gradients):
        d_W_hy, d_b_y, d_W, d_b = gradients
        self.W_hy -= self.eta * d_W_hy
        self.b_y -= self.eta * d_b_y
        self.W -= self.eta * d_W
        self.b -= self.eta * d_b

    def set_params(self, **params):
        super().set_params(**params)
        self.hidden_dim = self.embed_dim * 2
        return self

    def score(self, X, y):
        preds = self.predict(X)
        return utils.safe_macro_f1(y, preds)


def simple_example():
    from nltk.tree import Tree
    from sklearn.metrics import accuracy_score
    import utils

    utils.fix_random_seeds()

    train = [
        "(odd 1)",
        "(even 2)",
        "(even (odd 1) (neutral (neutral +) (odd 1)))",
        "(odd (odd 1) (neutral (neutral +) (even 2)))",
        "(odd (even 2) (neutral (neutral +) (odd 1)))",
        "(even (even 2) (neutral (neutral +) (even 2)))",
        "(even (odd 1) (neutral (neutral +) (odd (odd 1) (neutral (neutral +) (even 2)))))"
    ]

    test = [
        "(odd (odd 1))",
        "(even (even 2))",
        "(odd (odd 1) (neutral (neutral +) (even (odd 1) (neutral (neutral +) (odd 1)))))",
        "(even (even 2) (neutral (neutral +) (even (even 2) (neutral (neutral +) (even 2)))))",
        "(odd (even 2) (neutral (neutral +) (odd (even 2) (neutral (neutral +) (odd 1)))))",
        "(even (odd 1) (neutral (neutral +) (odd (even 2) (neutral (neutral +) (odd 1)))))",
        "(odd (even 2) (neutral (neutral +) (odd (odd 1) (neutral (neutral +) (even 2)))))"
    ]

    vocab = ["1", "+", "2"]

    X_train = [Tree.fromstring(x) for x in train]
    y_train = [t.label() for t in X_train]

    X_test = [Tree.fromstring(x) for x in test]
    y_test = [t.label() for t in X_test]

    mod = TreeNN(vocab)

    print(mod)

    mod.fit(X_train, y_train)

    print("\nTest predictions:")

    preds = mod.predict(X_test)

    correct = 0
    for tree, label, pred in zip(X_test, y_test, preds):
        correct += int(pred == label)
        print("{}\n\tPredicted: {}\n\tActual: {}".format(tree, pred, label))
    print("{}/{} correct".format(correct, len(X_test)))

    return accuracy_score(y_test, preds)


if __name__ == '__main__':
    simple_example()
