"""Base classes Param and Processor.

"""
import inspect
from types import FunctionType, MethodType, LambdaType
from abc import abstractmethod

from sprincl.io import DataStorageBase, NoStorage, NoDataSource, NoDataTarget
from ..base import Param
from ..plugboard import Plugboard


class Processor(Plugboard):
    """Base class of processors of tasks in a pipeline instance.

    Attributes
    ----------
    is_output : bool
        Assigned as :obj:`Param`, will be assigned as an instance attribute in `__init__`.
        Defines whether the Processor should yield an output for a Pipeline.
    is_checkpoint : bool
        Assigned as :obj:`Param`, will be assigned as an instance attribute in `__init__`.
        Defines whether checkpointed pipeline computations should start at this point, if there exists a previously
        computed checkpoint value.
    checkpoint_data : object
        If this Processor is a checkpoint, and if the Processor was called at least once, stores the output of this
        processor.

    """
    is_output = Param(bool, False)
    is_checkpoint = Param(bool, False)
    io = Param(DataStorageBase, NoStorage())

    def __init__(self, **kwargs):
        """Initialize all :obj:`Param` defined parameters to either there default value or, if supplied as keyword
        argument, to the value supplied.

        Parameters
        ----------
        is_checkpoint : bool
            Whether the Processor should yield an output for a Pipeline.
        is_output : bool
            Whether checkpointed pipeline computations should start at this point, if there exists a previously computed
            checkpoint value.
        **kwargs : dict
            Other potential parameters defined in sub classes.

        """
        super().__init__(**kwargs)
        self.checkpoint_data = None

    @abstractmethod
    def function(self, data):
        """Abstract function this Processor should apply on input

        Parameters
        ----------
        data : object
            Input data to this Processor.

        Raises
        ------
        NotImplementedError
            Always, since this is an abstract function.
        """

    def __call__(self, data):
        """Apply `self.funtion` on input data, save output if `self.is_checkpoint`

        Parameters
        ----------
        data : object
            Input data to this Processor.

        Returns
        -------
        object
            Depending on what operation `self.function` executes.

        """
        try:
            out = self.io.read()
        except NoDataSource:
            out = self.function(data)
            try:
                self.io.write(out)
            except NoDataTarget:
                pass
        if self.is_checkpoint:
            self.checkpoint_data = out
        return out

    def param_values(self):
        """Get values for all parameters defined through :obj:`Param` attributes.

        Returns
        -------
        dict of object
            Dict of the instance values of defined parameters.

        """
        return self.collect_attr(Param)

    def copy(self):
        """Copy self, creating a new Processor instance with the same values for :obj:`Param` attribute defined
        parameters.

        Returns
        -------
        :obj:`Processor`
            New instance with copied parameter values.

        """
        new = type(self)(**self.param_values())
        new.checkpoint_data = self.checkpoint_data
        return new

    @property
    def _output_repr(self):
        return 'output:np.ndarray'

    def __repr__(self):
        """Return Processor's representation.
        I.e.: ProcessorName(metric=sqeuclidean, function=lambda x: x.mean(1)) -> output: np.ndarray
        Replace self._output_repr for output representation. Default: output:np.ndarray.

        """

        def transform(x):
            """If x is a lambda function, return the source.

            """
            if isinstance(x, LambdaType):
                x = inspect.getsource(x).split('=', 1)[1].strip()
            return x

        name = self.__class__.__name__
        params = ', '.join(['{}={}'.format(k, transform(v)) for k, v in self.param_values().items() if v])
        return '{}({}) -> {}'.format(name, params, self._output_repr)


class FunctionProcessor(Processor):
    """Processor instance initialized with a supplied function

    Attributes
    ----------
    function : :obj:`types.FunctionType` or :obj:`types.MethodType`
        The function around which to create the :obj:`FunctionProcessor`. It wil be bound as a method if bind_method.
    bind_method : bool
        Will bind `function` to this class, enabling it to access `self`.

    """
    function = Param((MethodType, FunctionType), (lambda self, data: data))
    bind_method = Param(bool, False)

    def __init__(self, **kwargs):
        """Bind function as attribute of instance.

        See also
        --------
        :obj:`Processor`

        """
        super().__init__(**kwargs)
        if self.bind_method:
            self.function = self.function.__get__(self, type(self))


def ensure_processor(proc, **kwargs):
    """Make sure argument is a Processor and, if it is not, but callable, make it a FunctionProcessor. Set attributes of
    resulting processor as stated in `**kwargs`.

    Parameters
    ----------
    proc : Processor or callable
        Object to ensure to be a :obj:`Processor`.
    **kwargs :
        Keyword arguments stating new default values for Parameters of `proc`.

    Returns
    -------
    :obj:`Processor`
        Original object `proc` with updated attributes if it was a Processor, else a :obj:`FunctionProcessor` with
        supplied function.
        `proc` and attributes as given in `**kwargs`.

    """
    if not isinstance(proc, Processor):
        if callable(proc):
            proc = FunctionProcessor(function=proc)
        else:
            raise TypeError('Supplied processor {} is neither a Processor, nor callable!')
    proc.update_defaults(**kwargs)
    return proc
