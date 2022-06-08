# Copyright (c) 2021-2022, NVIDIA CORPORATION & AFFILIATES
#
# SPDX-License-Identifier: BSD-3-Clause

from types import MappingProxyType

from cirq import protocols, unitary, Circuit, MeasurementGate, Moment
import cupy as cp

from .tensor_wrapper import _get_backend_asarray_func

def remove_measurements(circuit):
    """
    Return a circuit with final measurement operations removed
    """
    circuit = circuit.copy()
    if circuit.has_measurements():
        if not circuit.are_all_measurements_terminal():
            raise ValueError('mid-circuit measurement not supported in tensor network simulation')
        else:
            predicate = lambda operation: isinstance(operation.gate, MeasurementGate)
            measurement_gates = list(circuit.findall_operations(predicate))
            circuit.batch_remove(measurement_gates)
    return circuit

def get_inverse_circuit(circuit):
    """
    Return a circuit with all gate operations inversed
    """
    return protocols.inverse(circuit)

def unfold_circuit(circuit, dtype='complex128', backend=cp):
    """
    Unfold the circuit to obtain the qubits and all gate tensors.

    Args:
        circuit: A :class:`cirq.Circuit` object. All parameters in the circuit must be resolved.
        dtype: Data type for the tensor operands.
        backend: The package the tensor operands belong to.

    Returns:
        All qubits and gate operations from the input circuit
    """
    qubits = sorted(circuit.all_qubits())
    asarray = _get_backend_asarray_func(backend)
    gates = []
    for moment in circuit.moments:
        for operation in moment:
            gate_qubits = operation.qubits
            tensor = unitary(operation).reshape((2,) * 2 * len(gate_qubits))
            tensor = asarray(tensor, dtype=dtype)
            gates.append([tensor, operation.qubits])
    return qubits, gates

def get_lightcone_circuit(circuit, coned_qubits):
    """
    Use unitary reversed lightcone cancellation technique to reduce the effective circuit size based on the qubits to be coned. 

    Args:
        circuit: A :class:`cirq.Circuit` object. 
        coned_qubits: An iterable of qubits to be coned.

    Returns:
        A :class:`cirq.Circuit` object that potentially contains less number of gates
    """
    coned_qubits = set(coned_qubits)
    n_qubits = len(circuit.all_qubits())
    moments = []
    reversed_moments = circuit.moments[::-1]
    n_moments = len(reversed_moments)
    for ix, moment in enumerate(reversed_moments):
        if len(coned_qubits) == n_qubits:
            moments.extend(reversed_moments[ix:])
            break
        reduced_moment = []
        reversed_operations = moment.operations[::-1]
        n_operations = len(reversed_operations)
        for iy, operation in enumerate(reversed_operations):
            if len(coned_qubits) == n_qubits:
                reduced_moment.extend(reversed_operations[iy:])
                break
            qubit_set = set(operation.qubits)
            if qubit_set & coned_qubits:
                reduced_moment.append(operation)
                coned_qubits |= qubit_set
        moments.append(Moment(reduced_moment[::-1]))
    newqc = Circuit(moments[::-1])
    return newqc
