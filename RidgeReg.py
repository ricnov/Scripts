import numpy as np

class LinearRegression:
    def __init__(self):
        self.theta = None
    def _cost(self, theta, X, y):
        X = np.array(X)
        y = np.array(y)
        theta = np.array(theta)

        return 1 / len(y) * sum([np.square(X.dot(theta) - y)])
    def fit(self, X, y):
        X = np.array(X)
        y = np.array(y)

        self.theta = np.linalg.inv(X.T.dot(X)).dot(X.T).dot(y)

        return self
    def predict(self, X):
        X = np.array(X)
        self.theta = np.array(self.theta)

        predictions = []

        for i in range(len(X)):
            result = []
            for j in range(len(self.theta)):
                result.append(self.theta[j] * X[i][j])
            predictions.append(sum(result))

        return predictions
    def score(self, X, y):
        predictons = self.predict(X)

        return sum(self._cost(self.theta, X, y)) / len(X)

class Ridge:
    def __init__(self):
        self.theta = None
    def _cost(self, theta, X, y):
        X = np.array(X)
        y = np.array(y)
        theta = np.array(theta)

        return 1 / len(y) * sum([np.square(X.dot(theta) - y)])
    def fit(self, X, y, lam):
        X = np.array(X)
        y = np.array(y)

        self.theta = np.linalg.inv(X.T.dot(X) + lam * np.identity(len(X.T))).dot(X.T).dot(y)

        return self
    def predict(self, X):
        X = np.array(X)
        self.theta = np.array(self.theta)

        predictions = []

        for i in range(len(X)):
            result = []
            for j in range(len(self.theta)):
                result.append(self.theta[j] * X[i][j])
            predictions.append(sum(result))

        return predictions
    def score(self, X, y):
        predictions = self.predict(X)

        return sum(self._cost(self.theta, X, y)) / len(X)
