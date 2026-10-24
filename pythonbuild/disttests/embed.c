#include <Python.h>

int
main(int argc, char **argv)
{
    Py_Initialize();
    int result = PyRun_SimpleString(argv[1]);
    return Py_FinalizeEx() < 0 || result != 0;
}
