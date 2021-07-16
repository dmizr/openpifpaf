import os
import sys

import numpy as np
import pytest
import torch

import openpifpaf
import openpifpaf.export_coreml


@pytest.mark.skipif(not sys.platform.startswith('darwin'), reason='coreml export only on macos')
def test_coreml_exportable(tmpdir):
    outfile = str(tmpdir.join('openpifpaf-shufflenetv2k16.coreml.mlmodel'))
    assert not os.path.exists(outfile)

    datamodule = openpifpaf.datasets.factory('cocokp')
    model, _ = openpifpaf.network.Factory(
        base_name='shufflenetv2k16',
    ).factory(head_metas=datamodule.head_metas)
    openpifpaf.export_coreml.apply(model, outfile)
    assert os.path.exists(outfile)


class ModuleWithOccupancy(openpifpaf.network.HeadNetwork):
    def __init__(self, meta, in_features):
        super().__init__(meta, in_features)
        self.occupancy = torch.classes.openpifpaf.Occupancy(1.0, 0.1)

    def forward(self, *args):
        x = args[0]
        # self.occupancy.clear()
        return x


@pytest.mark.skipif(not sys.platform.startswith('darwin'), reason='coreml export only on macos')
def test_coreml_torchscript(tmpdir):
    outfile = str(tmpdir.join('occupancy.coreml.mlmodel'))
    assert not os.path.exists(outfile)

    datamodule = openpifpaf.datasets.factory('cocokp')
    model, _ = openpifpaf.network.Factory(
        base_name='shufflenetv2k16',
    ).factory(head_metas=datamodule.head_metas)
    model.set_head_nets([
        ModuleWithOccupancy(model.head_metas[0], model.base_net.out_features),
        model.head_nets[1],
    ])

    openpifpaf.export_coreml.apply(model, outfile)
    assert os.path.exists(outfile)


class ModuleWithCifHr(openpifpaf.network.HeadNetwork):
    def __init__(self, meta, in_features):
        super().__init__(meta, in_features)
        self.cifhr = torch.classes.openpifpaf.CifHr()

    def forward(self, *args):
        x = args[0]
        with torch.no_grad():
            self.cifhr.reset(x.shape[1:], 8)
            self.cifhr.accumulate(x, 8, 0.0, 1.0)
        return x


@pytest.mark.skipif(not sys.platform.startswith('darwin'), reason='coreml export only on macos')
@pytest.mark.xfail  # custom classes not traceable: https://github.com/pytorch/pytorch/issues/47162
def test_coreml_torchscript_cifhr(tmpdir):
    outfile = str(tmpdir.join('cifhr.coreml.mlmodel'))
    assert not os.path.exists(outfile)

    datamodule = openpifpaf.datasets.factory('cocokp')
    model, _ = openpifpaf.network.Factory(
        base_name='shufflenetv2k16',
    ).factory(head_metas=datamodule.head_metas)
    model.set_head_nets([
        ModuleWithCifHr(model.head_metas[0], model.base_net.out_features),
        model.head_nets[1],
    ])

    openpifpaf.export_coreml.apply(model, outfile)
    assert os.path.exists(outfile)


class ModuleUsingCifHr(torch.nn.Module):
    def forward(self, x):  # pylint: disable=no-self-use
        cifhr = torch.classes.openpifpaf.CifHr()
        with torch.no_grad():
            cifhr.reset(x.shape[1:], 8)
            cifhr.accumulate(x[1:], 8, 0.0, 1.0)
        return x


@pytest.mark.skipif(not sys.platform.startswith('darwin'), reason='coreml export only on macos')
@pytest.mark.xfail  # custom classes not traceable: https://github.com/pytorch/pytorch/issues/47162
def test_coreml_torchscript_trace():
    head = ModuleUsingCifHr()

    dummy_input = torch.randn(1, 16, 17, 33)
    with torch.no_grad():
        traced_model = torch.jit.trace(head, dummy_input)

    assert traced_model is not None


@pytest.mark.skipif(not sys.platform.startswith('darwin'), reason='coreml export only on macos')
def test_trace_cifcaf_op():
    datamodule = openpifpaf.datasets.factory('cocokp')
    cifcaf_op = torch.ops.openpifpaf_decoder.cifcaf_op

    cif_field = torch.randn(datamodule.head_metas[0].n_fields, 5, 17, 33)
    caf_field = torch.randn(datamodule.head_metas[1].n_fields, 9, 17, 33)

    skeleton_m1 = torch.from_numpy(np.asarray(datamodule.head_metas[1].skeleton) - 1)

    with torch.no_grad():
        traced_model = torch.jit.trace(lambda ci, ca: cifcaf_op(
            datamodule.head_metas[0].n_fields,
            skeleton_m1,
            ci, 8,
            ca, 8,
            torch.empty((0, 17, 4)),
            torch.empty((0,), dtype=torch.int64),
        ), [
            cif_field,
            caf_field,
        ])

    assert traced_model is not None
