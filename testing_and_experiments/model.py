import os
import sys
import math
import random
import numpy as np
import tensorflow as tf
from past.builtins import xrange
import time as tim

class MemN2N(object):
    def __init__(self, config, sess):
        self.nwords = config.nwords
        self.batch_size = config.batch_size
        self.nepoch = config.nepoch
        self.nhop = config.nhop
        self.edim = config.edim
        self.LSTM_dim = config.LSTM_dim
        self.lindim = config.lindim
        self.rules_dim = config.rules_dim
        self.mem_size = config.mem_size
        self.max_grad_norm = config.max_grad_norm
        self.pad_idx = config.pad_idx
        self.pre_trained_context_wt = config.pre_trained_context_wt
        self.pre_trained_target_wt = config.pre_trained_target_wt
        self.input = tf.placeholder(tf.int32, [self.batch_size, 1], name="input")
        self.time = tf.placeholder(tf.int32, [None, self.mem_size], name="time")
        self.target = tf.placeholder(tf.int64, [self.batch_size], name="target")
        self.context = tf.placeholder(tf.int32, [self.batch_size, self.mem_size], name="context")
        self.mask = tf.placeholder(tf.float32, [self.batch_size, self.mem_size], name="mask")
        self.A = tf.placeholder(tf.float32, [self.nwords, self.edim], name="A") # Vocab * edim
        self.ASP = tf.placeholder(tf.float32, [self.pre_trained_target_wt.shape[0], self.edim], name="ASP") # V2 * edim

        self.neg_inf = tf.fill([self.batch_size, self.mem_size], -1*np.inf, name="neg_inf")

        self.W_rm      = tf.placeholder(tf.float32, [self.batch_size, self.rules_dim , self.mem_size], name="W_rm")

        self.show = config.show
        self.hid = []

        self.lr = None
        self.current_lr = config.init_lr
        self.loss = None
        self.step = None
        self.optim = None

        self.sess = sess
        self.log_loss = []
        self.log_perp = []

    def build_memory(self):
      self.global_step = tf.Variable(0, name="global_step")

      self.C = tf.Variable(tf.random_uniform([self.LSTM_dim, self.LSTM_dim], minval=-0.01, maxval=0.01)) #LSTM_dim * LSTM_dim
      self.C0 = tf.Variable(tf.random_uniform([self.edim, self.LSTM_dim], minval=-0.01, maxval=0.01)) #edim * LSTM_dim
      self.Att = tf.Variable(tf.random_uniform([1, self.rules_dim], minval=-0.01, maxval=0.01)) #1 * rules_dim
      self.GW = tf.Variable(tf.random_uniform([self.LSTM_dim, self.LSTM_dim], minval=-0.01, maxval=0.01)) #edim * LSTM_dim

      self.Ain_c = tf.nn.embedding_lookup(self.A, self.context) #batch_size * mem_size * edim


      self.ASPin = tf.nn.embedding_lookup(self.ASP, self.input) #batch_size * 1 * edim
      self.ASPout2dim = tf.reshape(self.ASPin, [-1, self.edim]) #batch_size * edim
      self.TransfASPout2dim = tf.matmul(self.ASPout2dim, self.C0) #batch_size * LSTM_dim
      # self.TransfASPout2dim = self.ASPout2dim #batch_size * LSTM_dim
      self.hid.append(self.TransfASPout2dim)    #batch_size * LSTM_dim

      self.LSTM_input = self.Ain_c #(batch_size , mem_size, e_dim)
      cell = tf.nn.rnn_cell.LSTMCell(self.LSTM_dim, state_is_tuple=True)
      outputs, state = tf.nn.dynamic_rnn(cell, \
                                        self.LSTM_input, \
                                        sequence_length=[self.mem_size]*self.batch_size, \
                                        dtype=tf.float32)


      # lstm_out = self.Ain_c
      # self.Ain = self.Ain_c #batch_size * mem_size * lstm_dim

      lstm_out = outputs
      self.Ain = outputs #batch_size * mem_size * lstm_dim
      # lstm_dim = self.edim


      # self.R = tf.matmul(self.W_rm, self.Ain_c) #batch_size * rules_dim * edim
      self.R = tf.matmul(self.W_rm, self.Ain) #batch_size * rules_dim * lstm_dim


      self.Att_dup = tf.tile(self.Att, [self.batch_size, 1]) #batch_size * 1 * rules_dim
      self.Att3dim = tf.reshape(self.Att_dup, [self.batch_size, 1, -1]) #batch_size * 1 * rule_dim
      self.Fout3dim = tf.matmul(self.Att3dim, self.R) #batch-size * 1 * lstm_dim
      self.Fout2dim = tf.reshape(self.Fout3dim, [self.batch_size, -1]) #batch_size * lstm_dim
      # self.hid.append(self.Fout2dim)


      for h in xrange(self.nhop):
        '''
        Bi-linear scoring function for a context word and aspect term
        '''
        # print h
        # print "hid",self.hid[-1]
        # self.til_hid = tf.tile(self.hid[-1], [1, self.mem_size]) #batch_size * LSTM_dim X mem_size X
        # self.til_hid3dim = tf.reshape(self.til_hid, [-1, self.mem_size, self.LSTM_dim]) ##batch_size * mem_size * LSTM_dim
        # self.a_til_concat = tf.concat(axis=2, values=[self.til_hid3dim, self.Ain]) #batch_size * mem_size * 2XLSTM_dim
        # self.til_bl_wt = tf.tile(self.BL_W, [self.batch_size, 1]) #batch_size X 2 X LSTM_dim * 1
        # self.til_bl_3dim = tf.reshape(self.til_bl_wt, [self.batch_size,  2 * self.LSTM_dim, -1]) #batch_size * 2 X LSTM_dim * 1
        # self.att = tf.matmul(self.a_til_concat, self.til_bl_3dim) #batch_size * mem_size * 1
        # self.til_bl_b = tf.tile(self.BL_B, [self.batch_size, self.mem_size]) #batch_size  *  mem_size
        # self.til_bl_3dim = tf.reshape(self.til_bl_b, [-1, self.mem_size, 1]) #batch_size  *  mem_size * 1
        # self.g = tf.nn.tanh(tf.add(self.att, self.til_bl_3dim)) #batch_size  *  mem_size * 1
        # self.g_2dim = tf.reshape(self.g, [-1, self.mem_size]) #batch_size  *  mem_size
        # self.masked_g_2dim = tf.add(self.g_2dim, self.mask)
        
        self.U3dim = tf.reshape(self.hid[-1], [-1, self.LSTM_dim, 1]) #bs * lstm_dim * 1
        self.att3dim = tf.matmul(self.Ain, self.U3dim) #batch_size * mem_size * 1
        self.att2dim = tf.reshape(self.att3dim, [-1, self.mem_size]) #batch_size * mem_size
        self.g_2dim = tf.nn.tanh(self.att2dim) #batch_size * mem_size

        self.masked_g_2dim = tf.multiply(self.g_2dim, self.mask) #batch_size  *  mem_size
        # self.masked_g_2dim = tf.add(self.g_2dim, self.mask) #batch_size  *  mem_size
        # self.P = tf.nn.softmax(self.masked_g_2dim)
        self.P = self.masked_g_2dim #batch_size  *  mem_size
        self.probs3dim = tf.reshape(self.P, [-1, 1, self.mem_size]) #batch_size * 1  *  mem_size


        self.Aout = tf.matmul(self.probs3dim, self.Ain) #batch_size * 1 * lstm_dim
        self.Aout2dim = tf.reshape(self.Aout, [self.batch_size, self.LSTM_dim]) #batch_size * lstm_dim
        
        #self.Fout2dim = tf.add(self.Aout2dim, self.Og2dim) #batch_size * lstm_dim
        self.total_att = tf.matmul(self.Aout2dim, self.GW) + self.Fout2dim #batch_size * lstm_dim

        Cout = tf.matmul(self.hid[-1], self.C) #batch_size * lstm_dim
        # til_C_B = tf.tile(self.C_B, [self.batch_size, 1])
        # Cout_add = tf.add(Cout, til_C_B)
        # self.Dout = tf.add(Cout_add, self.Fout2dim)

        self.Dout = tf.add(self.total_att, Cout) #batch_size * lstm_dim

        if self.lindim == self.edim:
            self.hid.append(self.Dout)
        elif self.lindim == 0:
            self.hid.append(tf.nn.relu(self.Dout))
        else:
            F = tf.slice(self.Dout, [0, 0], [self.batch_size, self.lindim])
            G = tf.slice(self.Dout, [0, self.lindim], [self.batch_size, self.edim-self.lindim])
            K = tf.nn.relu(G)
            self.hid.append(tf.concat(axis=1, values=[F, K]))
      

    def build_model(self):
      self.build_memory()

      self.W = tf.Variable(tf.random_uniform([self.LSTM_dim, 3], minval=-0.01, maxval=0.01)) #LSTM_dim * 3

      self.dropped_out = tf.nn.dropout(self.hid[-1], 0.4) 
      self.dropped_out = self.hid[-1]
      
      self.z = tf.matmul(self.dropped_out, self.W) #batch_size * 3
      
      self.loss = tf.nn.sparse_softmax_cross_entropy_with_logits(logits=self.z, labels=self.target)

      self.lr = tf.Variable(self.current_lr)
      self.opt = tf.train.AdagradOptimizer(self.lr)

      # params = [self.A, self.C, self.C_B, self.W, self.BL_W, self.BL_B]
      #params = [self.C0, self.C, self.W]
      params = None
      self.loss = tf.reduce_sum(self.loss) 

      grads_and_vars = self.opt.compute_gradients(self.loss, params)
      # clipped_grads_and_vars = [(tf.clip_by_norm(gv[0], self.max_grad_norm), gv[1]) \
      #                           for gv in grads_and_vars]
      clipped_grads_and_vars = grads_and_vars

      inc = self.global_step.assign_add(1)
      with tf.control_dependencies([inc]):
          self.optim = self.opt.apply_gradients(clipped_grads_and_vars)

      tf.initialize_all_variables().run()

      self.correct_prediction = tf.argmax(self.z, 1)

    def train(self, data):
      source_data, source_loc_data, target_data, target_label, orig_sent_data, W_rm_data = data

      N = int(math.ceil(len(source_data) / self.batch_size))
      cost = 0

      x = np.ndarray([self.batch_size, 1], dtype=np.int32)
      time = np.ndarray([self.batch_size, self.mem_size], dtype=np.int32)
      target = np.zeros([self.batch_size], dtype=np.int32) 
      context = np.ndarray([self.batch_size, self.mem_size], dtype=np.int32)
      mask = np.ndarray([self.batch_size, self.mem_size])
      W_rm = np.ndarray([self.batch_size, self.rules_dim , self.mem_size], dtype=np.float32)

      if self.show:
        from utils import ProgressBar
        bar = ProgressBar('Train', max=N)

      rand_idx, cur = np.random.permutation(len(source_data)), 0
      for idx in xrange(N):
        if self.show: bar.next()
        
        context.fill(self.pad_idx)
        time.fill(self.mem_size)
        target.fill(0)
        # mask.fill(-1.0*np.inf)
        mask.fill(0)
        

        for b in xrange(self.batch_size):
            m = rand_idx[cur]
            x[b][0] = target_data[m]
            target[b] = target_label[m]
            time[b,:len(source_loc_data[m])] = source_loc_data[m]
            context[b,:len(source_data[m])] = source_data[m]
            # mask[b,:len(source_data[m])].fill(0)
            mask[b,:len(source_data[m])].fill(1)

            crt_wrm = W_rm_data[m] # rules_dim * sen_len
            # print crt_wrm.shape
            W_rm[b] = np.pad(crt_wrm, [(0,0),(0,self.mem_size - crt_wrm.shape[1])], 'constant', constant_values = 0)
            cur = cur + 1
 
        _a, loss, self.step = self.sess.run([self.optim, self.loss,
                                            self.global_step],
                                            feed_dict={
                                                self.input: x,
                                                self.time: time,
                                                self.target: target,
                                                self.context: context,
                                                self.mask: mask,
                                                self.W_rm: W_rm,
                                                self.A:self.pre_trained_context_wt,
                                                self.ASP:self.pre_trained_target_wt})
        
       
        if idx == 0:
            print idx
            # print "asp - ", asp[0]
            # print "tasp - ", tasp[0]
            # print "A - ", kout
            # print "Ainc - ", kinc[0][:2][:20]
            # print "Ain - ", kin[0][:2][:20]
            # print "maskedZ - ", addedZ[0]
            # print "maskedZ - ", maskedZ[0]
            # print "dinv - ", dinv[:2][:20]
            # print "wma - ", wma[:2][:20]
            # print "Og - ", Ogg[:2][:20]
            # print "Z - ", Z[0]
            # print "ASPin - ", aspin
            # print "C0 - ", C0
            # print "U3dim - ", att[:2][:20]
            # #print "loss - ", loss
            # print "mask - ", mask[:2][:20]
            # print "Semantic Attention - ", P[:2][:20]
            # print "small z - " , z
            # print "dout - ", dout
            # print "dropped_out - ", do

        cost += np.sum(loss)
      
      if self.show: bar.finish()
      _, train_acc = self.test(data)
      return cost/N/self.batch_size, train_acc

    def test(self, data):
      source_data, source_loc_data, target_data, target_label, orig_sent_data, W_rm_data = data
      
      N = int(math.ceil(len(source_data) / self.batch_size))
      cost = 0

      x = np.ndarray([self.batch_size, 1], dtype=np.int32)
      time = np.ndarray([self.batch_size, self.mem_size], dtype=np.int32)
      target = np.zeros([self.batch_size], dtype=np.int32) 
      context = np.ndarray([self.batch_size, self.mem_size], dtype=np.int32)
      mask = np.ndarray([self.batch_size, self.mem_size])
      W_rm = np.ndarray([self.batch_size, self.rules_dim , self.mem_size], dtype=np.float32)

      context.fill(self.pad_idx)

      m, acc = 0, 0
      for i in xrange(N):
        target.fill(0)
        time.fill(self.mem_size)
        context.fill(self.pad_idx)
        # mask.fill(-1.0*np.inf)
        mask.fill(0)
        
        raw_labels = []
        for b in xrange(self.batch_size):
          x[b][0] = target_data[m]
          target[b] = target_label[m]
          time[b,:len(source_loc_data[m])] = source_loc_data[m]
          context[b,:len(source_data[m])] = source_data[m]
          # mask[b,:len(source_data[m])].fill(0)
          mask[b,:len(source_data[m])].fill(1)
          raw_labels.append(target_label[m])

          crt_wrm = W_rm_data[m]
          W_rm[b] = np.pad(crt_wrm, [(0,0),(0,self.mem_size - crt_wrm.shape[1])], 'constant', constant_values = 0)

          m += 1

        loss = self.sess.run([self.loss],
                                        feed_dict={
                                            self.input: x,
                                            self.time: time,
                                            self.target: target,
                                            self.context: context,
                                            self.mask: mask,
                                            self.W_rm: W_rm,
                                            self.A:self.pre_trained_context_wt,
                                            self.ASP:self.pre_trained_target_wt})
        cost += np.sum(loss)

        predictions = self.sess.run(self.correct_prediction, feed_dict={self.input: x,
                                                     self.time: time,
                                                     self.target: target,
                                                     self.context: context,
                                                     self.mask: mask,
                                                     self.W_rm: W_rm,
                                                     self.A:self.pre_trained_context_wt,
                                                     self.ASP:self.pre_trained_target_wt})

        for b in xrange(self.batch_size):
          if raw_labels[b] == predictions[b]:
            acc = acc + 1

      print 'predictions - ', predictions
      print 'labels - ', raw_labels
      return cost, acc/float(len(source_data))

    def run(self, train_data, test_data):
      print('training...')
      print self.pre_trained_context_wt.shape
      # self.sess.run(self.A.assign(self.pre_trained_context_wt))
      # self.sess.run(self.ASP.assign(self.pre_trained_target_wt))

      for idx in xrange(self.nepoch):
        print('epoch '+str(idx)+'...')
        train_loss, train_acc = self.train(train_data)
        test_loss, test_acc = self.test(test_data)
        print('train-loss=%.4f;train-acc=%.4f;test-acc=%.4f;' % (train_loss, train_acc, test_acc))
        self.log_loss.append([train_loss, test_loss])
        
