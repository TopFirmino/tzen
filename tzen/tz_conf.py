""" GVR: There is actually a hack that is occasionally used and recommended: a module can define a class with the desired functionality, 
    and then at the end, replace itself in sys.modules with an instance of that class (or with the class, if you insist, but that's generally less useful). """

from __future__ import annotations
import sys

class TZConfig:
    """ A class to manage configurations. """
    __VARS__ = {}
    __DEPENDENCY_TABLE__ = {}
    
    __all__ = list(__VARS__.keys())
    
    def __getattr__(self, name):
        
        if name in TZConfig.__VARS__:
            return TZConfig.__VARS__[name]
            
        else:
            raise AttributeError(f"Attribute {name} not found in TZConfig")
    
    def __setattr__(self, name, value):
        TZConfig.__VARS__[name] = value

    @staticmethod
    def use_config(*config_names):
        """ Declare the configuration variables to be used in the class. """
        
        def _wrapper(cls):
            if cls.__name__ not in TZConfig.__DEPENDENCY_TABLE__:
                TZConfig.__DEPENDENCY_TABLE__[cls.__name__] = config_names
            
            # Make sure to call the inject config function after the class is created
            # and before the __init__ function is called.
            _current_init = cls.__init__
            
            def __new__init__(self, *args, **kwargs):
                # Inject the configuration variables into the object
                TZConfig.inject_config(self)
                # Call the original __init__ function
                _current_init(self, *args, **kwargs)

            cls.__init__ = __new__init__
        
            return cls
    
        return _wrapper
    
    @staticmethod
    def verify_config_dependencies():
        """ Verify the dependencies of the configuration variables. """
        for k, v in TZConfig.__DEPENDENCY_TABLE__.items():
            for var in v:
                if var not in TZConfig.__VARS__:
                    raise ValueError(f"Configuration variable {var} is not defined in TZConfig")
    
    @staticmethod
    def inject_config(obj):
        """ Inject the configuration variables into the object. """
        # Verify if the object has dependencies
        if obj.__class__.__name__ in TZConfig.__DEPENDENCY_TABLE__:
            for var in TZConfig.__DEPENDENCY_TABLE__[obj.__class__.__name__]:
                # Inject the configuration variable into the object
                # if the variable is not already set in the object
                if var.lower() not in obj.__dict__:
                    setattr(obj, var.lower(), TZConfig.__VARS__[var])
                    
    
    
sys.modules[__name__] = TZConfig()
