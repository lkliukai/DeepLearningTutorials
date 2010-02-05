"""
 This tutorial introduces stacked denoising auto-encoders (SdA) using Theano.

 Denoising autoencoders are the building blocks for SDAE. 
 They are based on auto-encoders as the ones used in Bengio et al. 2007.
 An autoencoder takes an input x and first maps it to a hidden representation
 y = f_{\theta}(x) = s(Wx+b), parameterized by \theta={W,b}. The resulting 
 latent representation y is then mapped back to a "reconstructed" vector 
 z \in [0,1]^d in input space z = g_{\theta'}(y) = s(W'y + b').  The weight 
 matrix W' can optionally be constrained such that W' = W^T, in which case 
 the autoencoder is said to have tied weights. The network is trained such 
 that to minimize the reconstruction error (the error between x and z).

 For the denosing autoencoder, during training, first x is corrupted into 
 \tilde{x}, where \tilde{x} is a partially destroyed version of x by means 
 of a stochastic mapping. Afterwards y is computed as before (using 
 \tilde{x}), y = s(W\tilde{x} + b) and z as s(W'y + b'). The reconstruction 
 error is now measured between z and the uncorrupted input x, which is 
 computed as the cross-entropy : 
      - \sum_{k=1}^d[ x_k \log z_k + (1-x_k) \log( 1-z_k)]

 For X iteration of the main program loop it takes *** minutes on an 
 Intel Core i7 and *** minutes on GPU (NVIDIA GTX 285 graphics processor).


 References :
   - P. Vincent, H. Larochelle, Y. Bengio, P.A. Manzagol: Extracting and 
   Composing Robust Features with Denoising Autoencoders, ICML'08, 1096-1103,
   2008
   - Y. Bengio, P. Lamblin, D. Popovici, H. Larochelle: Greedy Layer-Wise
   Training of Deep Networks, Advances in Neural Information Processing 
   Systems 19, 2007

"""

import numpy 
import theano
import time
import theano.tensor as T
from theano.tensor.shared_randomstreams import RandomStreams

import gzip
import cPickle


class LogisticRegression(object):
    """Multi-class Logistic Regression Class

    The logistic regression is fully described by a weight matrix :math:`W` 
    and bias vector :math:`b`. Classification is done by projecting data 
    points onto a set of hyperplanes, the distance to which is used to 
    determine a class membership probability. 
    """

    def __init__(self, input, n_in, n_out):
        """ Initialize the parameters of the logistic regression
        :param input: symbolic variable that describes the input of the 
                      architecture (one minibatch)
        :type n_in: int
        :param n_in: number of input units, the dimension of the space in 
                     which the datapoints lie
        :type n_out: int
        :param n_out: number of output units, the dimension of the space in 
                      which the labels lie
        """ 

        # initialize with 0 the weights W as a matrix of shape (n_in, n_out) 
        self.W = theano.shared( value=numpy.zeros((n_in,n_out),
                                            dtype = theano.config.floatX) )
        # initialize the baises b as a vector of n_out 0s
        self.b = theano.shared( value=numpy.zeros((n_out,), 
                                            dtype = theano.config.floatX) )
        # compute vector of class-membership probabilities in symbolic form
        self.p_y_given_x = T.nnet.softmax(T.dot(input, self.W)+self.b)
        
        # compute prediction as class whose probability is maximal in 
        # symbolic form
        self.y_pred=T.argmax(self.p_y_given_x, axis=1)

        # list of parameters for this layer
        self.params = [self.W, self.b]

    def negative_log_likelihood(self, y):
        """Return the mean of the negative log-likelihood of the prediction
        of this model under a given target distribution.
        :param y: corresponds to a vector that gives for each example the
                  correct label
        Note: we use the mean instead of the sum so that
        the learning rate is less dependent on the batch size
        """
        return -T.mean(T.log(self.p_y_given_x)[T.arange(y.shape[0]),y])

    def errors(self, y):
        """Return a float representing the number of errors in the minibatch 
        over the total number of examples of the minibatch ; zero one
        loss over the size of the minibatch
        """
        # check if y has same dimension of y_pred 
        if y.ndim != self.y_pred.ndim:
            raise TypeError('y should have the same shape as self.y_pred', 
                ('y', target.type, 'y_pred', self.y_pred.type))

        # check if y is of the correct datatype        
        if y.dtype.startswith('int'):
            # the T.neq operator returns a vector of 0s and 1s, where 1
            # represents a mistake in prediction
            return T.mean(T.neq(self.y_pred, y))
        else:
            raise NotImplementedError()




class dA(object):
  """Denoising Auto-Encoder class (dA) 

  A denoising autoencoders tries to reconstruct the input from a corrupted 
  version of it by projecting it first in a latent space and reprojecting 
  it afterwards back in the input space. Please refer to Vincent et al.,2008
  for more details. If x is the input then equation (1) computes a partially
  destroyed version of x by means of a stochastic mapping q_D. Equation (2) 
  computes the projection of the input into the latent space. Equation (3) 
  computes the reconstruction of the input, while equation (4) computes the 
  reconstruction error.
  
  .. math::

    \tilde{x} ~ q_D(\tilde{x}|x)                                         (1)

    y = s(W \tilde{x} + b)                                               (2)

    x = s(W' y  + b')                                                    (3)

    L(x,z) = -sum_{k=1}^d [x_k \log z_k + (1-x_k) \log( 1-z_k)]          (4)

  """

  def __init__(self, n_visible= 784, n_hidden= 500, input= None):
    """
    Initialize the dA class by specifying the number of visible units (the 
    dimension d of the input ), the number of hidden units ( the dimension 
    d' of the latent or hidden space ) and by giving a symbolic variable 
    for the input. Such a symbolic variable is useful when the input is 
    the result of some computations. For example when dealing with SdAs,
    the dA on layer 2 gets as input the output of the DAE on layer 1. 
    This output can be written as a function of the input to the entire 
    model, and as such can be computed by theano whenever needed. 
    
    :param n_visible: number of visible units

    :param n_hidden:  number of hidden units

    :param input:     a symbolic description of the input or None 

    """
    self.n_visible = n_visible
    self.n_hidden  = n_hidden
    
    # create a Theano random generator that gives symbolic random values
    theano_rng = RandomStreams()
    # create a numpy random generator
    numpy_rng = numpy.random.RandomState()
    
     
    # initial values for weights and biases
    # note : W' was written as `W_prime` and b' as `b_prime`

    # W is initialized with `initial_W` which is uniformely sampled
    # from -6./sqrt(n_visible+n_hidden) and 6./sqrt(n_hidden+n_visible)
    # the output of uniform if converted using asarray to dtype 
    # theano.config.floatX so that the code is runable on GPU
    initial_W = numpy.asarray( numpy.random.uniform( \
              low = -numpy.sqrt(6./(n_visible+n_hidden)), \
              high = numpy.sqrt(6./(n_visible+n_hidden)), \
              size = (n_visible, n_hidden)), dtype = theano.config.floatX)
    initial_b       = numpy.zeros(n_hidden)
    initial_b_prime= numpy.zeros(n_visible)
     
    
    # theano shared variables for weights and biases
    self.W       = theano.shared(value = initial_W,       name = "W")
    self.b       = theano.shared(value = initial_b,       name = "b")
    # tied weights, therefore W_prime is W transpose
    self.W_prime = self.W.T 
    self.b_prime = theano.shared(value = initial_b_prime, name = "b'")

    # if no input is given, generate a variable representing the input
    if input == None : 
        # we use a matrix because we expect a minibatch of several examples,
        # each example being a row
        self.x = T.dmatrix(name = 'input') 
    else:
        self.x = input
    # Equation (1)
    # note : first argument of theano.rng.binomial is the shape(size) of 
    #        random numbers that it should produce
    #        second argument is the number of trials 
    #        third argument is the probability of success of any trial
    #
    #        this will produce an array of 0s and 1s where 1 has a 
    #        probability of 0.9 and 0 if 0.1
    self.tilde_x  = theano_rng.binomial( self.x.shape,  1,  0.9) * self.x
    # Equation (2)
    # note  : y is stored as an attribute of the class so that it can be 
    #         used later when stacking dAs. 
    self.y   = T.nnet.sigmoid(T.dot(self.tilde_x, self.W      ) + self.b)
    # Equation (3)
    self.z   = T.nnet.sigmoid(T.dot(self.y, self.W_prime) + self.b_prime)
    # Equation (4)
    self.L = - T.sum( self.x*T.log(self.z) + (1-self.x)*T.log(1-self.z), axis=1 ) 
    # note : L is now a vector, where each element is the cross-entropy cost 
    #        of the reconstruction of the corresponding example of the 
    #        minibatch. We need to compute the average of all these to get 
    #        the cost of the minibatch
    self.cost = T.mean(self.L)
    # note : y is computed from the corrupted `tilde_x`. Later on, 
    #        we will need the hidden layer obtained from the uncorrupted 
    #        input when for example we will pass this as input to the layer 
    #        above
    self.hidden_values = T.nnet.sigmoid( T.dot(self.x, self.W) + self.b)





class SdA():
    """Stacked denoising auto-encoder class (SdA)

    A stacked denoising autoencoder model is obtained by stacking several
    dAs. The hidden layer of the dA at layer `i` becomes the input of 
    the dA at layer `i+1`. The first layer dA gets as input the input of 
    the SdA, and the hidden layer of the last dA represents the output. 
    Note that after pretraining, the SdA is dealt with as a normal MLP, 
    the dAs are only used to initialize the weights.
    """

    def __init__(self, input, n_ins, hidden_layers_sizes, n_outs):
        """ This class is costum made for a three layer SdA, and therefore
        is created by specifying the sizes of the hidden layers of the 
        3 dAs used to generate the network. 

        :param input: symbolic variable describing the input of the SdA

        :param n_ins: dimension of the input to the sdA

        :param n_layers_sizes: intermidiate layers size, must contain 
        at least one value

        :param n_outs: dimension of the output of the network
        """
        
        self.layers =[]

        if len(hidden_layers_sizes) < 1 :
            raiseException (' You must have at least one hidden layer ')

        # add first layer:
        layer = dA(n_ins, hidden_layers_sizes[0], input = input)
        self.layers += [layer]
        # add all intermidiate layers
        for i in xrange( 1, len(hidden_layers_sizes) ):
            # input size is that of the previous layer
            # input is the output of the last layer inserted in our list 
            # of layers `self.layers`
            print i 
            print theano.pp(self.layers[-1].hidden_values)
            layer = dA( hidden_layers_sizes[i-1],             \
                        hidden_layers_sizes[i],               \
                        input = self.layers[-1].hidden_values )
            self.layers += [layer]
        

        self.n_layers = len(self.layers)
        print '------------------------------------------'
        print theano.pp(self.layers[-1].hidden_values)
        # now we need to use same weights and biases to define an MLP
        # We can simply use the `hidden_values` of the top layer, which 
        # computes the input that we would normally feed to the logistic
        # layer on top of the MLP and just add a logistic regression on 
        # this values
        
        # add a logistic layer on top
        self.logLayer = LogisticRegression(\
                         input = self.layers[-1].hidden_values,\
                         n_in = hidden_layers_sizes[-1], n_out = n_outs)


    def negative_log_likelihood(self, y):
        """Return the mean of the negative log-likelihood of the prediction
        of this model under a given target distribution. In our case this 
        is given by the logistic layer.

        :param y: corresponds to a vector that gives for each example the
        :correct label
        """
        return self.logLayer.negative_log_likelihood(y)

    def errors(self, y):
        """Return a float representing the number of errors in the minibatch 
        over the total number of examples of the minibatch 
        """
        
        return self.logLayer.errors(y)

  

def sgd_optimization_mnist( learning_rate=0.1, pretraining_epochs = 5, \
                            pretraining_lr = 0.1, training_epochs = 1000, dataset='mnist.pkl.gz'):
    """
    Demonstrate stochastic gradient descent optimization for a multilayer 
    perceptron

    This is demonstrated on MNIST.

    :param learning_rate: learning rate used (factor for the stochastic 
    gradient

    :param pretraining_epochs: number of epoch to do pretraining

    :param pretrain_lr: learning rate to be used during pre-training

    :param n_iter: maximal number of iterations ot run the optimizer 

    :param dataset: path the the pickled dataset

    """

    # Load the dataset 
    f = gzip.open(dataset,'rb')
    train_set, valid_set, test_set = cPickle.load(f)
    f.close()


    def shared_dataset(data_xy):
        data_x, data_y = data_xy
        shared_x = theano.shared(numpy.asarray(data_x, dtype=theano.config.floatX))
        shared_y = theano.shared(numpy.asarray(data_y, dtype=theano.config.floatX))
        return shared_x, T.cast(shared_y, 'int32')

    test_set_x, test_set_y = shared_dataset(test_set)
    valid_set_x, valid_set_y = shared_dataset(valid_set)
    train_set_x, train_set_y = shared_dataset(train_set)

    batch_size = 20    # size of the minibatch

    # compute number of minibatches for training, validation and testing
    n_train_batches = train_set_x.value.shape[0] / batch_size
    n_valid_batches = valid_set_x.value.shape[0] / batch_size
    n_test_batches  = test_set_x.value.shape[0]  / batch_size

    # allocate symbolic variables for the data
    index = T.lscalar()    # index to a [mini]batch 
    x     = T.matrix('x')  # the data is presented as rasterized images
    y     = T.ivector('y') # the labels are presented as 1D vector of 
                           # [int] labels




    # construct the logistic regression class
    classifier = SdA( input=x, n_ins=28*28, \
                      hidden_layers_sizes = [500, 500, 500], n_outs=10)
    
    ## Pre-train layer-wise 
    for i in xrange(classifier.n_layers):
        # compute gradients of layer parameters
        gW       = T.grad(classifier.layers[i].cost, classifier.layers[i].W)
        gb       = T.grad(classifier.layers[i].cost, classifier.layers[i].b)
        gb_prime = T.grad(classifier.layers[i].cost, \
                                               classifier.layers[i].b_prime)
        # updated value of parameters after each step
        new_W       = classifier.layers[i].W      - gW      * pretraining_lr
        new_b       = classifier.layers[i].b      - gb      * pretraining_lr
        new_b_prime = classifier.layers[i].b_prime- gb_prime* pretraining_lr
        cost = classifier.layers[i].cost
        print '---------------------------------------------------'
        print ' Layer : ',i
        print ' x : ', theano.pp(classifier.layers[i].x)
        print ' '
        print ' tilde_x: ', theano.pp(classifier.layers[i].tilde_x)
        print ' '
        print 'y :', theano.pp(classifier.layers[i].y)
        print ' '
        print 'z: ', theano.pp(classifier.layers[i].z)
        print ' '
        print 'L:', theano.pp(classifier.layers[i].L)
        print ' '
        print 'cost: ', theano.pp(classifier.layers[i].cost)
        print ' '
        print 'hid: ', theano.pp(classifier.layers[i].hidden_values)
        print '================================================='
        layer_update = theano.function([index], [cost, classifier.layers[i].x, classifier.layers[i].z], \
          updates = { 
              classifier.layers[i].W       : new_W \
            , classifier.layers[i].b       : new_b \
            , classifier.layers[i].b_prime : new_b_prime },
          givens = {
              x :train_set_x[index*batch_size:(index+1)*batch_size]})
        # go through pretraining epochs 
        for epoch in xrange(pretraining_epochs):
            # go through the training set
            for batch_index in xrange(n_train_batches):
                c = layer_update(batch_index)
            print 'Pre-training layer %i, epoch %d'%(i,epoch),c, batch_index



    # Fine-tune the entire model
    # the cost we minimize during training is the negative log likelihood of 
    # the model
    cost = classifier.negative_log_likelihood(y) 

    # compiling a theano function that computes the mistakes that are made  
    # by the model on a minibatch
    # create a function to compute the mistakes that are made by the model
    test_model = theano.function([index], classifier.errors(y),
             givens = {
               x: test_set_x[index*batch_size:(index+1)*batch_size],
               y: test_set_y[index*batch_size:(index+1)*batch_size]})

    validate_model = theano.function([index], classifier.errors(y),
            givens = {
               x: valid_set_x[index*batch_size:(index+1)*batch_size],
               y: valid_set_y[index*batch_size:(index+1)*batch_size]})


    # compute the gradient of cost with respect to theta and add them to the 
    # updates list
    updates = []
    for i in xrange(classifier.n_layers):        
        g_W   = T.grad(cost, classifier.layers[i].W)
        g_b   = T.grad(cost, classifier.layers[i].b)
        new_W = classifier.layers[i].W - learning_rate * g_W
        new_b = classifier.layers[i].b - learning_rate * g_b
        updates += [ (classifier.layers[i].W, new_W) \
                   , (classifier.layers[i].b, new_b) ]
    # add the gradients of the logistic layer
    g_log_W   = T.grad(cost, classifier.logLayer.W)
    g_log_b   = T.grad(cost, classifier.logLayer.b)
    new_log_W = classifier.logLayer.W - learning_rate * g_log_W
    new_log_b = classifier.logLayer.b - learning_rate * g_log_b
    updates += [ (classifier.logLayer.W, new_log_W) \
               , (classifier.logLayer.b, new_log_b) ]

    # compiling a theano function `train_model` that returns the cost, but  
    # in the same time updates the parameter of the model based on the rules 
    # defined in `updates`
    train_model = theano.function([index], cost, updates=updates,
          givens = {
            x: train_set_x[index*batch_size:(index+1)*batch_size],
            y: train_set_y[index*batch_size:(index+1)*batch_size]})

    # early-stopping parameters
    patience              = 10000 # look as this many examples regardless
    patience_increase     = 2     # wait this much longer when a new best is 
                                  # found
    improvement_threshold = 0.995 # a relative improvement of this much is 
                                  # considered significant
    validation_frequency  = min(n_train_batches, patience/2)
                                  # go through this many 
                                  # minibatche before checking the network 
                                  # on the validation set; in this case we 
                                  # check every epoch 


    best_params          = None
    best_validation_loss = float('inf')
    test_score           = 0.
    start_time = time.clock()
    cost_ij = []
    for epoch in xrange(training_epochs):
      for minibatch_index in xrange(n_train_batches):

        cost_ij += [train_model(minibatch_index)]
        iter    = epoch * n_train_batches + minibatch_index

        if (iter+1) % validation_frequency == 0: 
            print cost_ij
            cost_ij = []
            validation_losses = [validate_model(i) for i in xrange(n_valid_batches)]
            print validation_losses
            this_validation_loss = numpy.mean(validation_losses)
            print('epoch %i, minibatch %i/%i, validation error %f %%' % \
                   (epoch, minibatch_index+1, n_train_batches, \
                    this_validation_loss*100.))


            # if we got the best validation score until now
            if this_validation_loss < best_validation_loss:

                #improve patience if loss improvement is good enough
                if this_validation_loss < best_validation_loss *  \
                       improvement_threshold :
                    patience = max(patience, iter * patience_increase)

                # save best validation score and iteration number
                best_validation_loss = this_validation_loss
                best_iter = iter

                # test it on the test set
                test_losses = [test_model(i) for i in xrange(n_test_batches)]
                test_score = numpy.mean(test_losses)
                print(('     epoch %i, minibatch %i/%i, test error of best '
                      'model %f %%') % 
                             (epoch, minibatch_index+1, n_train_batches,
                              test_score*100.))


        if patience <= iter :
                break

    end_time = time.clock()
    print(('Optimization complete with best validation score of %f %%,'
           'with test performance %f %%') %  
                 (best_validation_loss * 100., test_score*100.))
    print ('The code ran for %f minutes' % ((end_time-start_time)/60.))






if __name__ == '__main__':
    sgd_optimization_mnist()

