#include <dlfcn.h>
#include <stdio.h>

int
main(int argc, char **argv)
{
    void *stub = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    if (stub == NULL) {
        fprintf(stderr, "%s\n", dlerror());
        return 1;
    }
    void (*initialize)(void) = dlsym(stub, "Py_Initialize");
    int (*run)(const char *) = dlsym(stub, "PyRun_SimpleString");
    int (*finalize)(void) = dlsym(stub, "Py_FinalizeEx");
    if (initialize == NULL || run == NULL || finalize == NULL) {
        return 1;
    }
    initialize();
    int result = run("import sys; print(sys.base_prefix)");
    return finalize() < 0 || result != 0;
}
