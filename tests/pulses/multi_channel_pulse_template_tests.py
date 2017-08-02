import unittest

import numpy

from qctoolkit.pulses.pulse_template_parameter_mapping import MissingMappingException,\
    MissingParameterDeclarationException, UnnecessaryMappingException
from qctoolkit.pulses.parameters import ParameterNotProvidedException, MappedParameter, ConstantParameter
from qctoolkit.pulses.multi_channel_pulse_template import MultiChannelPulseTemplate, MultiChannelWaveform, MappingTemplate, ChannelMappingException, AtomicMultiChannelPulseTemplate
from qctoolkit.expressions import Expression
from qctoolkit.pulses.instructions import CHANInstruction, EXECInstruction

from tests.pulses.sequencing_dummies import DummySequencer, DummyInstructionBlock, DummyPulseTemplate, DummyWaveform
from tests.serialization_dummies import DummySerializer
from tests.pulses.pulse_template_tests import PulseTemplateStub

class MultiChannelWaveformTest(unittest.TestCase):

    def test_init_no_args(self) -> None:
        with self.assertRaises(ValueError):
            MultiChannelWaveform(dict())
        with self.assertRaises(ValueError):
            MultiChannelWaveform(None)

    def test_init_single_channel(self) -> None:
        dwf = DummyWaveform(duration=1.3, defined_channels={'A'})

        waveform = MultiChannelWaveform([dwf])
        self.assertEqual({'A'}, waveform.defined_channels)
        self.assertEqual(1.3, waveform.duration)

    def test_init_several_channels(self) -> None:
        dwf_a = DummyWaveform(duration=2.2, defined_channels={'A'})
        dwf_b = DummyWaveform(duration=2.2, defined_channels={'B'})
        dwf_c = DummyWaveform(duration=2.3, defined_channels={'C'})

        waveform = MultiChannelWaveform([dwf_a, dwf_b])
        self.assertEqual({'A', 'B'}, waveform.defined_channels)
        self.assertEqual(2.2, waveform.duration)

        with self.assertRaises(ValueError):
            MultiChannelWaveform([dwf_a, dwf_c])
        with self.assertRaises(ValueError):
            MultiChannelWaveform([waveform, dwf_c])
        with self.assertRaises(ValueError):
            MultiChannelWaveform((dwf_a, dwf_a))

        dwf_c_valid = DummyWaveform(duration=2.2, defined_channels={'C'})
        waveform_flat = MultiChannelWaveform((waveform, dwf_c_valid))
        self.assertEqual(len(waveform_flat.compare_key), 3)

    def test_unsafe_sample(self) -> None:
        sample_times = numpy.linspace(98.5, 103.5, num=11)
        samples_a = numpy.linspace(4, 5, 11)
        samples_b = numpy.linspace(2, 3, 11)
        dwf_a = DummyWaveform(duration=3.2, sample_output=samples_a, defined_channels={'A'})
        dwf_b = DummyWaveform(duration=3.2, sample_output=samples_b, defined_channels={'B', 'C'})
        waveform = MultiChannelWaveform((dwf_a, dwf_b))

        result_a = waveform.unsafe_sample('A', sample_times)
        numpy.testing.assert_equal(result_a, samples_a)

        result_b = waveform.unsafe_sample('B', sample_times)
        numpy.testing.assert_equal(result_b, samples_b)

        self.assertEqual(len(dwf_a.sample_calls), 1)
        self.assertEqual(len(dwf_b.sample_calls), 1)

        numpy.testing.assert_equal(sample_times, dwf_a.sample_calls[0][1])
        numpy.testing.assert_equal(sample_times, dwf_b.sample_calls[0][1])

        self.assertEqual('A', dwf_a.sample_calls[0][0])
        self.assertEqual('B', dwf_b.sample_calls[0][0])

        self.assertIs(dwf_a.sample_calls[0][2], None)
        self.assertIs(dwf_b.sample_calls[0][2], None)

        reuse_output = numpy.empty_like(samples_a)
        result_a = waveform.unsafe_sample('A', sample_times, reuse_output)
        self.assertEqual(len(dwf_a.sample_calls), 2)
        self.assertIs(result_a, reuse_output)
        self.assertIs(result_a, dwf_a.sample_calls[1][2])
        numpy.testing.assert_equal(result_b, samples_b)

    def test_equality(self) -> None:
        dwf_a = DummyWaveform(duration=246.2, defined_channels={'A'})
        dwf_b = DummyWaveform(duration=246.2, defined_channels={'B'})
        dwf_c = DummyWaveform(duration=246.2, defined_channels={'C'})
        waveform_a1 = MultiChannelWaveform([dwf_a, dwf_b])
        waveform_a2 = MultiChannelWaveform([dwf_a, dwf_b])
        waveform_a3 = MultiChannelWaveform([dwf_a, dwf_c])
        self.assertEqual(waveform_a1, waveform_a1)
        self.assertEqual(waveform_a1, waveform_a2)
        self.assertNotEqual(waveform_a1, waveform_a3)

    def test_get_measurement_windows(self):
        def meas_window(i):
            return str(int(i)), i, i+1

        dwf_a = DummyWaveform(duration=246.2, defined_channels={'A'},
                              measurement_windows=[meas_window(1), meas_window(2)])
        dwf_b = DummyWaveform(duration=246.2, defined_channels={'B'},
                              measurement_windows=[meas_window(3), meas_window(4), meas_window(5)])
        dwf_c = DummyWaveform(duration=246.2, defined_channels={'C'})

        mcwf = MultiChannelWaveform((dwf_a, dwf_b, dwf_c))
        expected_windows = set(meas_window(i) for i in range(1, 6))
        received_windows = tuple(mcwf.get_measurement_windows())
        self.assertEqual(len(received_windows), 5)
        self.assertEqual(set(received_windows), expected_windows)

    def test_unsafe_get_subset_for_channels(self):
        dwf_a = DummyWaveform(duration=246.2, defined_channels={'A'})
        dwf_b = DummyWaveform(duration=246.2, defined_channels={'B'})
        dwf_c = DummyWaveform(duration=246.2, defined_channels={'C'})

        mcwf = MultiChannelWaveform((dwf_a, dwf_b, dwf_c))
        with self.assertRaises(KeyError):
            mcwf.unsafe_get_subset_for_channels({'D'})
        with self.assertRaises(KeyError):
            mcwf.unsafe_get_subset_for_channels({'A', 'D'})

        self.assertIs(mcwf.unsafe_get_subset_for_channels({'A'}), dwf_a)
        self.assertIs(mcwf.unsafe_get_subset_for_channels({'B'}), dwf_b)
        self.assertIs(mcwf.unsafe_get_subset_for_channels({'C'}), dwf_c)

        sub_ab = mcwf.unsafe_get_subset_for_channels({'A', 'B'})
        self.assertEqual(sub_ab.defined_channels, {'A', 'B'})
        self.assertIsInstance(sub_ab, MultiChannelWaveform)
        self.assertIs(sub_ab.unsafe_get_subset_for_channels({'A'}), dwf_a)
        self.assertIs(sub_ab.unsafe_get_subset_for_channels({'B'}), dwf_b)


class AtomicMultiChannelPulseTemplateTest(unittest.TestCase):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)

        self.subtemplates = [DummyPulseTemplate(parameter_names={'p1'},
                                                measurement_names={'m1'},
                                                defined_channels={'c1'}),
                             DummyPulseTemplate(parameter_names={'p2'},
                                                measurement_names={'m2'},
                                                defined_channels={'c2'}),
                             DummyPulseTemplate(parameter_names={'p3'},
                                                measurement_names={'m3'},
                                                defined_channels={'c3'})]
        self.no_param_maps = [{'p1': '1'}, {'p2': '2'}, {'p3': '3'}]
        self.param_maps = [{'p1': 'pp1'}, {'p2': 'pp2'}, {'p3': 'pp3'}]
        self.chan_maps = [{'c1': 'cc1'}, {'c2': 'cc2'}, {'c3': 'cc3'}]

    def test_init_empty(self) -> None:
        with self.assertRaises(ValueError):
            AtomicMultiChannelPulseTemplate()

        with self.assertRaises(ValueError):
            AtomicMultiChannelPulseTemplate(identifier='foo')

        with self.assertRaises(ValueError):
            AtomicMultiChannelPulseTemplate(external_parameters=set())

        with self.assertRaises(ValueError):
            AtomicMultiChannelPulseTemplate(identifier='foo', external_parameters=set())

        with self.assertRaises(ValueError):
            AtomicMultiChannelPulseTemplate(identifier='foo', external_parameters=set(), parameter_constraints=[])

    def test_non_atomic_subtemplates(self):
        non_atomic_pt = PulseTemplateStub(duration='t1', defined_channels={'A'}, parameter_names=set())
        atomic_pt = DummyPulseTemplate(defined_channels={'B'}, duration='t1')

        with self.assertRaises(TypeError):
            AtomicMultiChannelPulseTemplate(non_atomic_pt)

        with self.assertRaises(TypeError):
            AtomicMultiChannelPulseTemplate(non_atomic_pt, atomic_pt)

        with self.assertRaises(TypeError):
            AtomicMultiChannelPulseTemplate(MappingTemplate(non_atomic_pt), atomic_pt)

        with self.assertRaises(TypeError):
            AtomicMultiChannelPulseTemplate((non_atomic_pt, {'B': 'C'}), atomic_pt)

    def test_duration(self):
        sts = [DummyPulseTemplate(duration='t1', defined_channels={'A'}),
               DummyPulseTemplate(duration='t1', defined_channels={'B'}),
               DummyPulseTemplate(duration='t2', defined_channels={'C'})]
        with self.assertRaises(ValueError):
            AtomicMultiChannelPulseTemplate(*sts)

        with self.assertRaises(ValueError):
            AtomicMultiChannelPulseTemplate(sts[0], sts[2])
        template = AtomicMultiChannelPulseTemplate(*sts[:1])

        self.assertEqual(template.duration, 't1')

    def test_external_parameters(self):
        sts = [DummyPulseTemplate(duration='t1', defined_channels={'A'}, parameter_names={'a', 'b'}),
               DummyPulseTemplate(duration='t1', defined_channels={'B'}, parameter_names={'a', 'c'})]
        constraints = ['a < d']
        template = AtomicMultiChannelPulseTemplate(*sts,
                                                   parameter_constraints=constraints,
                                                   external_parameters={'a', 'b', 'c', 'd'})

        with self.assertRaises(MissingParameterDeclarationException):
            AtomicMultiChannelPulseTemplate(*sts,
                                            external_parameters={'a', 'c', 'd'},
                                            parameter_constraints=constraints)
        with self.assertRaises(MissingParameterDeclarationException):
            AtomicMultiChannelPulseTemplate(*sts, external_parameters={'a', 'b', 'd'},
                                            parameter_constraints=constraints)
        with self.assertRaises(MissingParameterDeclarationException):
            AtomicMultiChannelPulseTemplate(*sts, external_parameters={'b', 'c', 'd'},
                                            parameter_constraints=constraints)
        with self.assertRaises(MissingParameterDeclarationException):
            AtomicMultiChannelPulseTemplate(*sts, external_parameters={'a', 'c', 'b'},
                                            parameter_constraints=constraints)

        with self.assertRaises(MissingMappingException):
            AtomicMultiChannelPulseTemplate(*sts, external_parameters={'a', 'b', 'c', 'd', 'e'},
                                            parameter_constraints=constraints)

        self.assertEqual(template.parameter_names, {'a', 'b', 'c', 'd'})

    def test_mapping_template_pure_conversion(self):
        template = AtomicMultiChannelPulseTemplate(*zip(self.subtemplates, self.param_maps, self.chan_maps))

        for st, pm, cm in zip(template.subtemplates, self.param_maps, self.chan_maps):
            self.assertEqual(st.parameter_names, set(pm.values()))
            self.assertEqual(st.defined_channels, set(cm.values()))

    def test_mapping_template_mixed_conversion(self):
        subtemp_args = [
            (self.subtemplates[0], self.param_maps[0], self.chan_maps[0]),
            MappingTemplate(self.subtemplates[1], parameter_mapping=self.param_maps[1], channel_mapping=self.chan_maps[1]),
            (self.subtemplates[2], self.param_maps[2], self.chan_maps[2])
        ]
        template = AtomicMultiChannelPulseTemplate(*subtemp_args)

        for st, pm, cm in zip(template.subtemplates, self.param_maps, self.chan_maps):
            self.assertEqual(st.parameter_names, set(pm.values()))
            self.assertEqual(st.defined_channels, set(cm.values()))

    def test_channel_intersection(self):
        chan_maps = self.chan_maps.copy()
        chan_maps[-1]['c3'] = 'cc1'
        with self.assertRaises(ChannelMappingException):
            AtomicMultiChannelPulseTemplate(*zip(self.subtemplates, self.param_maps, chan_maps))

    def test_defined_channels(self):
        subtemp_args = [*zip(self.subtemplates, self.param_maps, self.chan_maps)]
        template = AtomicMultiChannelPulseTemplate(*subtemp_args)
        self.assertEqual(template.defined_channels, {'cc1', 'cc2', 'cc3'})


class MultiChannelPulseTemplateTest(unittest.TestCase):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)

        self.subtemplates = [DummyPulseTemplate(parameter_names={'p1'}, measurement_names={'m1'}, defined_channels={'c1'},
                                          requires_stop=True,  is_interruptable=False),
                             DummyPulseTemplate(parameter_names={'p2'}, measurement_names={'m2'}, defined_channels={'c2'},
                                          requires_stop=False, is_interruptable=True),
                             DummyPulseTemplate(parameter_names={'p3'}, measurement_names={'m3'}, defined_channels={'c3'},
                                          requires_stop=False, is_interruptable=True)]
        self.no_param_maps = [{'p1': '1'}, {'p2': '2'}, {'p3': '3'}]
        self.param_maps = [{'p1': 'pp1'}, {'p2': 'pp2'}, {'p3': 'pp3'}]
        self.chan_maps = [{'c1': 'cc1'}, {'c2': 'cc2'}, {'c3': 'cc3'}]

    def test_init_empty(self) -> None:
        with self.assertRaises(ValueError):
            MultiChannelPulseTemplate([], {}, identifier='foo')

    def test_mapping_template_pure_conversion(self):
        subtemp_args = [*zip(self.subtemplates, self.param_maps, self.chan_maps)]
        template = MultiChannelPulseTemplate(subtemp_args, external_parameters={'pp1', 'pp2', 'pp3'})

        for st, pm, cm in zip(template.subtemplates, self.param_maps, self.chan_maps):
            self.assertEqual(st.parameter_names, set(pm.values()))
            self.assertEqual(st.defined_channels, set(cm.values()))

    def test_mapping_template_mixed_conversion(self):
        subtemp_args = [
            (self.subtemplates[0], self.param_maps[0], self.chan_maps[0]),
            MappingTemplate(self.subtemplates[1], parameter_mapping=self.param_maps[1], channel_mapping=self.chan_maps[1]),
            (self.subtemplates[2], self.param_maps[2], self.chan_maps[2])
        ]
        template = MultiChannelPulseTemplate(subtemp_args, external_parameters={'pp1', 'pp2', 'pp3'})

        for st, pm, cm in zip(template.subtemplates, self.param_maps, self.chan_maps):
            self.assertEqual(st.parameter_names, set(pm.values()))
            self.assertEqual(st.defined_channels, set(cm.values()))

    def test_channel_intersection(self):
        chan_maps = self.chan_maps.copy()
        chan_maps[-1]['c3'] = 'cc1'
        with self.assertRaises(ChannelMappingException):
            MultiChannelPulseTemplate(zip(self.subtemplates, self.param_maps, chan_maps), external_parameters={'pp1', 'pp2', 'pp3'})

    def test_external_parameter_error(self):
        subtemp_args = [*zip(self.subtemplates, self.param_maps, self.chan_maps)]
        with self.assertRaises(MissingParameterDeclarationException):
            MultiChannelPulseTemplate(subtemp_args, external_parameters={'pp1', 'pp2'})
        with self.assertRaises(MissingMappingException):
            MultiChannelPulseTemplate(subtemp_args, external_parameters={'pp1', 'pp2', 'pp3', 'foo'})

    def test_defined_channels(self):
        subtemp_args = [*zip(self.subtemplates, self.param_maps, self.chan_maps)]
        template = MultiChannelPulseTemplate(subtemp_args, external_parameters={'pp1', 'pp2', 'pp3'})
        self.assertEqual(template.defined_channels, {'cc1', 'cc2', 'cc3'})

    def test_is_interruptable(self):
        subtemp_args = [*zip(self.subtemplates, self.no_param_maps, self.chan_maps)]

        self.assertFalse(
            MultiChannelPulseTemplate(subtemp_args, external_parameters=set()).is_interruptable)

        self.assertTrue(
            MultiChannelPulseTemplate(subtemp_args[1:], external_parameters=set()).is_interruptable)


class MultiChannelPulseTemplateSequencingTests(unittest.TestCase):

    def test_requires_stop_false_mapped_parameters(self) -> None:
        dummy = DummyPulseTemplate(parameter_names={'foo'})
        pulse = MultiChannelPulseTemplate([(dummy, dict(foo='2*bar'), {'default': 'A'}),
                                           (dummy, dict(foo='rab-5'), {'default': 'B'})],
                                          {'bar', 'rab'})
        self.assertEqual({'bar', 'rab'}, pulse.parameter_names)

        parameters = dict(bar=ConstantParameter(-3.6), rab=ConstantParameter(35.26))
        self.assertFalse(pulse.requires_stop(parameters, dict()))

    def test_requires_stop_true_mapped_parameters(self) -> None:
        dummy = DummyPulseTemplate(parameter_names={'foo'}, requires_stop=True)
        pulse = MultiChannelPulseTemplate([(dummy, dict(foo='2*bar'), {'default': 'A'}),
                                           (dummy, dict(foo='rab-5'), {'default': 'B'})],
                                          {'bar', 'rab'})
        self.assertEqual({'bar', 'rab'}, pulse.parameter_names)
        parameters = dict(bar=ConstantParameter(-3.6), rab=ConstantParameter(35.26))
        self.assertTrue(pulse.requires_stop(parameters, dict()))

    def test_build_sequence_different_duration(self) -> None:
        dummy_wf1 = DummyWaveform(duration=2.4, defined_channels={'A'})
        dummy_wf2 = DummyWaveform(duration=2.3, defined_channels={'B'})
        dummy1 = DummyPulseTemplate(parameter_names={'bar'}, defined_channels={'A'}, waveform=dummy_wf1, duration=2.4)
        dummy2 = DummyPulseTemplate(parameter_names={}, defined_channels={'B'}, waveform=dummy_wf2, duration=2.3)

        sequencer = DummySequencer()
        pulse = MultiChannelPulseTemplate([dummy1, dummy2], {'bar'})

        parameters = {'bar': ConstantParameter(3)}
        measurement_mapping = {}
        channel_mapping = {'A': 'A', 'B': 'B'}
        instruction_block = DummyInstructionBlock()
        conditions = {}

        pulse.build_sequence(sequencer, parameters=parameters,
                                        conditions=conditions,
                                        measurement_mapping=measurement_mapping,
                                        channel_mapping=channel_mapping,
                                        instruction_block=instruction_block)

        self.assertEqual(len(instruction_block), 2)
        self.assertIsInstance(instruction_block[0], CHANInstruction)

        for chan, sub_block_ptr in instruction_block[0].channel_to_instruction_block.items():
            self.assertIn(chan,('A', 'B'))
            if chan == 'A':
                self.assertEqual( sequencer.sequencing_stacks[sub_block_ptr.block],
                                  [(dummy1, parameters, conditions, measurement_mapping, channel_mapping)])
            if chan == 'B':
                self.assertEqual(sequencer.sequencing_stacks[sub_block_ptr.block],
                                 [(dummy2, parameters, conditions, measurement_mapping, channel_mapping)])

    def test_build_sequence_same_duration(self) -> None:
        dummy_wf1 = DummyWaveform(duration=2.3, defined_channels={0})
        dummy_wf2 = DummyWaveform(duration=2.3, defined_channels={'B'})
        dummy1 = DummyPulseTemplate(parameter_names={'bar'}, defined_channels={0}, waveform=dummy_wf1, duration=2.3)
        dummy2 = DummyPulseTemplate(parameter_names={}, defined_channels={'B'}, waveform=dummy_wf2, duration=2.3)

        sequencer = DummySequencer()
        pulse = MultiChannelPulseTemplate([dummy1, dummy2], {'bar'})

        parameters = {'bar': ConstantParameter(3)}
        measurement_mapping = {}
        channel_mapping = {0: 1, 'B': 'B'}
        instruction_block = DummyInstructionBlock()
        conditions = {}

        pulse.build_sequence(sequencer, parameters=parameters,
                                        conditions=conditions,
                                        measurement_mapping=measurement_mapping,
                                        channel_mapping=channel_mapping,
                                        instruction_block=instruction_block)

        self.assertEqual(len(instruction_block), 2)
        self.assertIsInstance(instruction_block[0], EXECInstruction)
        self.assertIsInstance(instruction_block[0].waveform, MultiChannelWaveform)

        self.assertEqual(instruction_block[0].waveform.compare_key, (dummy_wf1.compare_key, dummy_wf2.compare_key))


class MultiChannelPulseTemplateSerializationTests(unittest.TestCase):

    def __init__(self, methodName) -> None:
        super().__init__(methodName=methodName)
        self.maxDiff = None
        self.dummy1 = DummyPulseTemplate(parameter_names={'foo'}, defined_channels={'A'}, measurement_names={'meas_1'})
        self.dummy2 = DummyPulseTemplate(parameter_names={}, defined_channels={'B', 'C'})

    def test_get_serialization_data(self) -> None:
        serializer = DummySerializer(
            serialize_callback=lambda x: str(x) if isinstance(x, Expression) else str(id(x)))
        template = MultiChannelPulseTemplate(
            [ self.dummy1, self.dummy2 ],
            {'foo'},
            identifier='herbert'
        )
        template.atomicity = True
        expected_data = dict(
            subtemplates=[str(id(self.dummy1)), str(id(self.dummy2))],
            atomicity=True,
            type=serializer.get_type_identifier(template))
        data = template.get_serialization_data(serializer)
        self.assertEqual(expected_data, data)

    def test_deserialize(self) -> None:
        serializer = DummySerializer(serialize_callback=lambda x: str(x) if isinstance(x, Expression) else str(id(x)))
        serializer.subelements[str(id(self.dummy1))] = self.dummy1
        serializer.subelements[str(id(self.dummy2))] = self.dummy2

        data = dict(
            subtemplates=[str(id(self.dummy1)), str(id(self.dummy2))],
            atomicity=False)

        template = MultiChannelPulseTemplate.deserialize(serializer, **data)
        for st_expected, st_found in zip( [self.dummy1, self.dummy2], template.subtemplates ):
            self.assertEqual(st_expected,st_found)
