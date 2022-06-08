# Copyright (c) 2021-2022, NVIDIA CORPORATION & AFFILIATES
#
# SPDX-License-Identifier: BSD-3-Clause

__all__ = ['backends', 'dtypes', 'cirq', 'cirq_circuits', 'qiskit', 'qiskit_circuits', 'CirqTester', 'QiskitTester']

from types import MappingProxyType

try:
    import cirq
except ImportError:
    cirq = None
import cupy as cp
import numpy as np
try:
    import torch
except:
    torch = None
try:
    import qiskit
except:
    qiskit = None

from cuquantum import contract, CircuitToEinsum
from .testutils import allclose

np.random.seed(3)

dtypes = ['complex64', 
          'complex128']
if torch:
    backends = [np, cp, torch]
else:
    backends = [np, cp, 'torch'] # marked as string to be skipped

cirq_circuits = []
qiskit_circuits = []

BASE_SYMBOLS = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
EMPTY_DICT = MappingProxyType(dict())
def gen_qubits_map(qubits):
    n_qubits = len(qubits)
    if n_qubits > len(BASE_SYMBOLS):
        raise NotImplementedError(f'small test only support up to {len(BASE_SYMBOLS)} qubits')
    qubits_map = dict(zip(qubits, BASE_SYMBOLS[:n_qubits]))
    return qubits_map

def bitstring_generator(n_qubits, nsample=1):
    for _ in range(nsample):
        bitstring = ''.join(np.random.choice(('0', '1'), n_qubits))
        yield bitstring
        
def where_fixed_generator(qubits, nfix_max, nsite_max=None):
    indices = np.arange(len(qubits))
    for nfix in range(nfix_max):
        np.random.shuffle(indices)
        fixed_sites = [qubits[indices[ix]] for ix in range(nfix)]
        bitstring = ''.join(np.random.choice(('0', '1'), nfix))
        fixed = dict(zip(fixed_sites, bitstring))
        if nsite_max is None:
            yield fixed
        else:
            for nsite in range(1, nsite_max):
                where = [qubits[indices[ix]] for ix in range(nfix, nfix+nsite)]
                yield where, fixed

def get_partial_indices(qubits, fixed):
    partial_indices = [slice(None)] * len(qubits)
    index_map = {'0': slice(0, 1),
                 '1': slice(1, 2)}
    for ix, q in enumerate(qubits):
        if q in fixed:
            partial_indices[ix] = index_map[fixed[q]]
    return partial_indices

################################################
# functions to generate cirq.Circuit for testing
################################################

def get_cirq_qft_circuit(n_qubits):
    qubits = cirq.LineQubit.range(n_qubits)
    qreg = list(qubits)[::-1]
    operations = []
    while len(qreg) > 0:
        q_head = qreg.pop(0)
        operations.append(cirq.H(q_head))
        for i, qubit in enumerate(qreg):
            operations.append((cirq.CZ ** (1 / 2 ** (i + 1)))(qubit, q_head))
    circuit = cirq.Circuit(operations)
    return circuit

def get_cirq_random_circuit(n_qubits, n_moments, op_density=0.9, seed=3):
    return cirq.testing.random_circuit(n_qubits, n_moments, op_density, random_state=seed)

N_QUBITS_RANGE = range(7, 9)
N_MOMENTS_RANGE = DEPTH_RANGE = range(5, 7)

if cirq:
    for n_qubits in N_QUBITS_RANGE:
        cirq_circuits.append(get_cirq_qft_circuit(n_qubits))
        for n_moments in N_MOMENTS_RANGE:
            cirq_circuits.append(get_cirq_random_circuit(n_qubits, n_moments))

#########################################################
# functions to generate qiskit.QuantumCircuit for testing
#########################################################

def get_qiskit_qft_circuit(n_qubits):
    return qiskit.circuit.library.QFT(n_qubits, do_swaps=False).decompose()

def get_qiskit_random_circuit(n_qubits, depth):
    from qiskit.circuit.random import random_circuit
    circuit = random_circuit(n_qubits, depth, max_operands=3)
    return circuit

def get_qiskit_composite_circuit():
    sub_q = qiskit.QuantumRegister(2)
    sub_circ = qiskit.QuantumCircuit(sub_q, name='sub_circ')
    sub_circ.h(sub_q[0])
    sub_circ.crz(1, sub_q[0], sub_q[1])
    sub_circ.barrier()
    sub_circ.id(sub_q[1])
    sub_circ.u(1, 2, -2, sub_q[0])

    # Convert to a gate and stick it into an arbitrary place in the bigger circuit
    sub_inst = sub_circ.to_instruction()

    qr = qiskit.QuantumRegister(3, 'q')
    circ = qiskit.QuantumCircuit(qr)
    circ.h(qr[0])
    circ.cx(qr[0], qr[1])
    circ.cx(qr[1], qr[2])
    circ.append(sub_inst, [qr[1], qr[2]])
    circ.append(sub_inst, [qr[0], qr[2]])
    circ.append(sub_inst, [qr[0], qr[1]])
    return circ

def get_qiskit_nested_circuit():
    qr = qiskit.QuantumRegister(6, 'q')
    circ = qiskit.QuantumCircuit(qr)
    sub_ins = get_qiskit_composite_circuit().to_instruction()
    circ.append(sub_ins, [qr[0], qr[2], qr[4]])
    circ.append(sub_ins, [qr[1], qr[3], qr[5]])
    circ.cx(qr[0], qr[3])
    circ.cx(qr[1], qr[4])
    circ.cx(qr[2], qr[5])
    return circ

if qiskit:
    qiskit_circuits.append(get_qiskit_composite_circuit())
    qiskit_circuits.append(get_qiskit_nested_circuit())
    for n_qubits in N_QUBITS_RANGE:
        qiskit_circuits.append(get_qiskit_qft_circuit(n_qubits))
        for depth in DEPTH_RANGE:
            qiskit_circuits.append(get_qiskit_random_circuit(n_qubits, depth))

###################################################################
#
# Simulator APIs inside cirq and qiskit may be subject to change.
# Version tests are needed. In cases where simulator API changes,
# the implementatitons to be modified are: 
# `CirqTest._get_state_vector_from_simulator` and 
# `QiskitTest._get_state_vector_from_simulator`
#
###################################################################


class BaseTester:
    def __init__(self, circuit, dtype, backend, nsample, nsite_max, nfix_max):
        self.circuit = circuit
        self.converter = CircuitToEinsum(circuit, dtype=dtype, backend=backend)
        self.backend = backend
        self.qubits = self.converter.qubits
        self.n_qubits = self.converter.n_qubits
        self.dtype = dtype
        self.sv = None
        self.nsample = nsample
        self.nsite_max = max(1, min(nsite_max, self.n_qubits-1))
        self.nfix_max = max(min(nfix_max, self.n_qubits-nsite_max-1), 0)
        
    def get_state_vector_from_simulator(self, fixed=EMPTY_DICT):
        if self.sv is None:
            self.sv = self._get_state_vector_from_simulator()
        if fixed:
            partial_indices = get_partial_indices(self.qubits, fixed)
            sv = self.sv[tuple(partial_indices)]
            return sv.reshape((2,)*(self.n_qubits-len(fixed)))
        else:
            return self.sv
    
    def get_amplitude_from_simulator(self, bitstring):
        sv = self.get_state_vector_from_simulator()
        index = [int(ibit) for ibit in bitstring]
        return sv[tuple(index)]
    
    def get_reduced_density_matrix_from_simulator(self, where, fixed=EMPTY_DICT):
        """
        For where = (a, b), reduced density matrix is formulated as:
        :math: `rho_{a,b,a^{\prime},b^{\prime}}  = \sum_{c,d,e,...} SV^{\star}_{a^{\prime}, b^{\prime}, c, d, e, ...} SV_{a, b, c, d, e, ...}`
        """
        sv = self.get_state_vector_from_simulator()
        partial_indices = get_partial_indices(self.qubits, fixed)
        sv = sv[tuple(partial_indices)]
        
        qubits_map = gen_qubits_map(self.qubits)
        output_inds = ''.join([qubits_map[q] for q in where])
        output_inds += output_inds.upper()
        left_inds = ''.join([qubits_map[q] for q in self.qubits])
        right_inds = ''
        for q in self.qubits:
            if q in where:
                right_inds += qubits_map[q].upper()
            else:
                right_inds += qubits_map[q]
        expression = left_inds + ',' + right_inds + '->' + output_inds
        if self.backend is torch:
            rdm = contract(expression, sv, sv.conj().resolve_conj())
        else:
            rdm = contract(expression, sv, sv.conj())
        return rdm
        
    def _get_state_vector_from_simulator(self):
        raise NotImplementedError
                
    def test_state_vector(self):
        for fixed in where_fixed_generator(self.qubits, self.nfix_max):
            expression, operands = self.converter.state_vector(fixed=fixed)
            sv1 = contract(expression, *operands)
            sv2 = self.get_state_vector_from_simulator(fixed=fixed)
            allclose(self.backend.__name__, self.dtype, sv1, sv2)
    
    def test_bitstrings(self):
        for bitstring in bitstring_generator(self.n_qubits, self.nsample):    
            expression, operands = self.converter.amplitude(bitstring)
            amp1 = contract(expression, *operands)
            amp2 = self.get_amplitude_from_simulator(bitstring)
            allclose(self.backend.__name__, self.dtype, amp1, amp2)
    
    def test_reduced_density_matrices(self):
        for where, fixed in where_fixed_generator(self.qubits, self.nfix_max, nsite_max=self.nsite_max):
            expression1, operands1 = self.converter.reduced_density_matrix(where, fixed=fixed, lightcone=True)
            expression2, operands2 = self.converter.reduced_density_matrix(where, fixed=fixed, lightcone=False)
            assert len(operands1) <= len(operands2)            
            rdm1 = contract(expression1, *operands1)
            rdm2 = contract(expression2, *operands2)
            rdm3 = self.get_reduced_density_matrix_from_simulator(where, fixed=fixed)

            allclose(self.backend.__name__, self.dtype, rdm1, rdm3)
            allclose(self.backend.__name__, self.dtype, rdm2, rdm3)

    def run_tests(self):
        self.test_state_vector()
        self.test_bitstrings()
        self.test_reduced_density_matrices()


class CirqTester(BaseTester):
    def _get_state_vector_from_simulator(self):
        qubits = self.qubits
        simulator = cirq.Simulator(dtype=self.dtype)
        result = simulator.simulate(self.circuit, qubit_order=qubits)
        statevector = result.state_vector().reshape((2,)*self.n_qubits)
        if self.backend is torch:
            statevector = torch.as_tensor(statevector, dtype=getattr(torch, self.dtype), device='cuda')
        else:
            statevector = self.backend.asarray(statevector, dtype=self.dtype)
        return statevector


class QiskitTester(BaseTester):    
    def _get_state_vector_from_simulator(self):
        # requires qiskit >= 0.24.0
        precision = {'complex64': 'single',
                     'complex128': 'double'}[self.dtype]
        try:
            # for qiskit >= 0.25.0
            simulator = qiskit.Aer.get_backend('aer_simulator_statevector', precision=precision)
            circuit = qiskit.transpile(self.circuit, simulator)
            circuit.save_statevector()
            result = simulator.run(circuit).result()
        except:
            # for qiskit 0.24.*
            circuit = self.circuit
            simulator = qiskit.Aer.get_backend('statevector_simulator', precision=precision)
            result = qiskit.execute(circuit, simulator).result()
        sv = np.asarray(result.get_statevector()).reshape((2,)*circuit.num_qubits)
        # statevector returned by qiskit's simulator is labelled by the inverse of :attr:`qiskit.QuantumCircuit.qubits`
        # this is different from `cirq` and different from the implementation in :class:`CircuitToEinsum`
        sv = sv.transpose(list(range(circuit.num_qubits))[::-1])
        if self.backend is torch:
            sv = torch.as_tensor(sv, dtype=getattr(torch, self.dtype), device='cuda')
        else:
            sv = self.backend.asarray(sv, dtype=self.dtype)
        return sv

