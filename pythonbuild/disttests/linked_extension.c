#include <Python.h>

static PyObject *
none(PyObject *self, PyObject *unused)
{
    Py_RETURN_NONE;
}

static PyMethodDef methods[] = {
    {"none", none, METH_NOARGS, NULL},
    {NULL}
};

static PyModuleDef_Slot slots[] = {{Py_mod_gil, Py_MOD_GIL_NOT_USED}, {0}};
static PyModuleDef module = {
    PyModuleDef_HEAD_INIT, "_linked", NULL, 0, methods, slots,
};

PyMODINIT_FUNC
PyInit__linked(void)
{
    return PyModuleDef_Init(&module);
}
