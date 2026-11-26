import unittest
import torch
from docurecon_v122f_train_improved import HeightAwareDateCRNN
from docurecon_v122d_train_crnn import encode, decode_greedy

class TestHeightAwareCRNN(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)
    def test_output_shape(self):
        model=HeightAwareDateCRNN().eval()
        with torch.no_grad():
            y=model(torch.rand(2,1,48,320))
        self.assertEqual(tuple(y.shape),(80,2,14))
    def test_log_probabilities(self):
        model=HeightAwareDateCRNN().eval()
        with torch.no_grad():
            y=model(torch.rand(1,1,48,320))
        self.assertTrue(torch.allclose(y.exp().sum(dim=2),torch.ones(80,1),atol=1e-5))
    def test_gradients(self):
        model=HeightAwareDateCRNN()
        y=model(torch.rand(1,1,48,320))
        target=torch.tensor(encode('05.07.2020'),dtype=torch.long)
        loss=torch.nn.CTCLoss(blank=0,zero_infinity=False)(y,target,torch.tensor([80]),torch.tensor([10]))
        self.assertTrue(bool(torch.isfinite(loss)))
        loss.backward()
        self.assertIsNotNone(model.cnn[0].weight.grad)
    def test_blank_decoder(self):
        logits=torch.full((80,1,14),-10.0)
        logits[:,:,0]=0
        self.assertEqual(decode_greedy(logits),[''])

if __name__=='__main__': unittest.main()
