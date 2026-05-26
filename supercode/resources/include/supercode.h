#ifndef SUPERCODE_H
#define SUPERCODE_H

#ifdef SUPERCODE_IDE

#ifndef super_export_func
#define super_export_func(name, return_type, ...) return_type name(__VA_ARGS__)
#endif

#ifndef super_import_func
#define super_import_func(name, return_type, ...) return_type name(__VA_ARGS__)
#endif

#ifndef super_struct
#define super_struct(name)
#endif

#ifndef super_func
#define super_func(return_type, ...) ((return_type)0)
#endif

#else

#ifndef SUPERCODE_RESOLVED
#error "SuperCode holes were not resolved. Build with `super`."
#endif

#ifndef super_export_func
#define super_export_func(name, return_type, ...) return_type name(__VA_ARGS__)
#endif

#ifndef super_import_func
#define super_import_func(name, return_type, ...) return_type name(__VA_ARGS__)
#endif

#ifndef super_struct
#define super_struct(name) \
    typedef struct name name; \
    name *name##_create(void); \
    void name##_destroy(name *v); \
    void name##_push(name *v, int x); \
    int name##_get(const name *v, int index); \
    int name##_size(const name *v)
#endif

#ifndef super_func
#define super_func(return_type, ...) SUPERCODE__UNMAPPED_super_func(__LINE__)
#endif

#endif

#endif
