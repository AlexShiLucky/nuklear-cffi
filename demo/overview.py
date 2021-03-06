"""
Python port of the nuklear 'overview()' function.

Note: here be bugs!  The main goal here was to port 'overview.c' over to
Python to make sure that it's possible to do everything you need to do from
the Python end.  Correctly porting over the *logic* was a secondary concern!

The C implementation is a single, very long function that relies heavily on
local static variables for storage.  In C this is absolutely fine, but we don't
have local statics in Python.  I got around this by dynamically adding fields to
an object as necessary, but *names are not scoped*  and the original overview
function often re-uses the same name.

I was going to go through and uniquify all of the names, but it seems to work as
it is, and as outlined above, I don't care so much about logic bugs on the
calling side - just that the nuklear API can be called.  So I've left it in
the present state.

I did consider parsing overview.c and generating the Python automatically, but
in the end I decided it might be simpler to do it by hand - which was an absolute
ballache and took forever, but was fairly simple.  I didn't opt for parsing
since I suspected I would end up trying to parse arbtrary C and things would get
quite complicated.  So I sat and typed the damn thing out by hand. Pity me.

Future things to consider

   * Generate this automatically by parsing overview.c
   * Tidy up the 'declare()' mess, uniquify names etc.
   * Extract some quality of life things to 'pynk' proper.
       - Field address access
       - Tree ID generation
   * Make certain things easier:
       - Wrap up properties to avoid ffi.new() everywhere.
   * Ensure the cffi 'unions by value' issue is not  a problem.
       
"""

import pynk
import datetime
import math
import inspect
import sys

INT_MAX = sys.maxint
INT_MIN = -sys.maxint - 1

class Overview(object):
    """
    Python port of the nuklear 'overview()' function.  It's a class, not a
    function, because we use member variables instead of C statics.
    """

    def __init__(self):
        """
        Constructor.  Note - fields on this class are added dynamically from
        inside the 'overview()' function, so we don't do much here.
        """
        self.__strings = []

    def declare(self, name, initialiser, ctype=None):
        """
        Poor man's 'static' declaration: adds a member variable to the object
        called 'name', initialising it based on the given 'initialiser' and
        'ctype' string.
        
        :param name: Name of the new field.
        :param initialiser: Initial value or 0-argument callable returning it.
        :param ctype: If present, a c type string for a cffi Cdata object.
        :return: Nothing.
        
        The original nuklear overview.c relies heavily on C static lifetime
        and scope.  In C, you can introduce a static variable (that will persist
        for the lifetime of the program) in a scope - and it will only pollute
        the namespace for that scope; you can create another static with the
        same name in a different scope later on and that's fine.  This also
        means that, in a long function, you can introduce the (static) storage
        for a bit of code right there next to it.
        
        We don't have that in Python.  This method gets us the second benefit 
        (declare storage at the point where it's used in a large function) but
         there's nothing we can do about the first thing - we just have to pick 
         our names carefully.
        """
        if not hasattr(self, name):
            value = initialiser
            if callable(value):
                value = value()
            if ctype is not None:
                value = pynk.ffi.new(ctype, value)
            setattr(self, name, value)

    def declare_string_array(self, name, lst):
        """ 
        Method to declare() a c array of static strings, as it's very
        laborious and tricky. 
        :param name: Name of the new field.
        :param lst: List of strings.
        """
        keepalive = [pynk.ffi.new("const char[]", s) for s in lst]
        self.__strings += keepalive
        self.declare(name, keepalive, "const char*[]")

    def declare_string_buffers(self, name, num_strings, string_length):
        """ Method to declare an array of string buffers. """
        keepalive = [pynk.ffi.new("char[%s]" % string_length) for i in xrange(num_strings)]
        self.__strings += keepalive
        self.declare(name, keepalive, "char*[]")

    def tree_push(self, ctx, tree_type, title, state, unique_id_str):
        """ The 'nk_tree_push' macro generates a unique ID for your tree based on the
        current line number and file name.  But in Python we don't have the C preprocessor,
        but we can get this information by inspecting the call stack. """
        # See https://stackoverflow.com/questions/6810999/how-to-determine-file-function-and-line-number/6811020
        callerframerecord = inspect.stack()[1]
        frame = callerframerecord[0]
        info = inspect.getframeinfo(frame)
        return pynk.lib.nk_tree_push_hashed(ctx, tree_type, title, state, info.filename, len(info.filename), info.lineno)

    def get_field_cdata(self, cdata, name_str):
        """ Make it easy to get the address of a field in a deeply nested struct. """
        names = name_str.split(".")
        for name in names:
            cdata = pynk.ffi.addressof(cdata, name)
        return cdata

    #
    # static int
    # overview(struct nk_context *ctx)
    # {
    def overview(self, ctx):
        """
        Python port of the nuklear 'overview()' function.  This gives a demo
        of the capabilities of the nuklear library.
        :param ctx: A nuklear context.
        :return: Nothing.
        """
        # /* window flags */
        # static int show_menu = nk_true;
        # static int titlebar = nk_true;
        # static int border = nk_true;
        # static int resize = nk_true;
        # static int movable = nk_true;
        # static int no_scrollbar = nk_false;
        # static int scale_left = nk_false;
        # static nk_flags window_flags = 0;
        # static int minimizable = nk_true;
        self.declare("show_menu", 1, "int*")
        self.declare("titlebar", 1, "int*")
        self.declare("border", 1, "int*")
        self.declare("resize", 1, "int*")
        self.declare("movable", 1, "int*")
        self.declare("no_scrollbar", 0, "int*")
        self.declare("scale_left", 0, "int*")
        self.declare("window_flags", 0, "int*")
        self.declare("minimizable", 1, "int*")


        #
        # /* popups */
        # static enum nk_style_header_align header_align = NK_HEADER_RIGHT;
        # static int show_app_about = nk_false;
        self.declare("header_align", pynk.lib.NK_HEADER_RIGHT)
        self.declare("show_app_about", False)

        #
        # /* window flags */
        # window_flags = 0;
        # ctx->style.window.header.align = header_align;
        # if (border) window_flags |= NK_WINDOW_BORDER;
        # if (resize) window_flags |= NK_WINDOW_SCALABLE;
        # if (movable) window_flags |= NK_WINDOW_MOVABLE;
        # if (no_scrollbar) window_flags |= NK_WINDOW_NO_SCROLLBAR;
        # if (scale_left) window_flags |= NK_WINDOW_SCALE_LEFT;
        # if (minimizable) window_flags |= NK_WINDOW_MINIMIZABLE;
        self.window_flags[0] = 0
        ctx.style.window.header.align = self.header_align
        if self.border[0]: self.window_flags[0] |= pynk.lib.NK_HEADER_RIGHT
        if self.resize[0]: self.window_flags[0] |= pynk.lib.NK_WINDOW_SCALABLE
        if self.movable[0]: self.window_flags[0] |= pynk.lib.NK_WINDOW_MOVABLE
        if self.no_scrollbar[0]: self.window_flags[0] |= pynk.lib.NK_WINDOW_NO_SCROLLBAR
        if self.scale_left[0]: self.window_flags[0] |= pynk.lib.NK_WINDOW_SCALE_LEFT
        if self.minimizable[0]: self.window_flags[0] |= pynk.lib.NK_WINDOW_MINIMIZABLE

        #
        # if (nk_begin(ctx, "Overview", nk_rect(10, 10, 400, 600), window_flags))
        # {
        if pynk.lib.nk_begin(ctx, "PyOverview", pynk.lib.nk_rect(10, 10, 400, 600), self.window_flags[0]):
            # if (show_menu)
            # {
            if self.show_menu:
                # /* menubar */
                # enum menu_states {MENU_DEFAULT, MENU_WINDOWS};
                # static nk_size mprog = 60;
                # static int mslider = 10;
                # static int mcheck = nk_true;
                # nk_menubar_begin(ctx);
                MENU_DEFAULT = 0
                MENU_WINDOWS = 1
                self.declare("mprog", 60, "nk_size*")
                self.declare("mslider", 10, "int*")
                self.declare("mcheck", 0, "int*")
                pynk.lib.nk_menubar_begin(ctx)

                #
                # /* menu #1 */
                # nk_layout_row_begin(ctx, NK_STATIC, 25, 5);
                # nk_layout_row_push(ctx, 45);
                # if (nk_menu_begin_label(ctx, "MENU", NK_TEXT_LEFT, nk_vec2(120, 200)))
                # {
                pynk.lib.nk_layout_row_begin(ctx, pynk.lib.NK_STATIC, 25, 5)
                pynk.lib.nk_layout_row_push(ctx, 45)
                if pynk.lib.nk_menu_begin_label(ctx, "MENU", pynk.lib.NK_TEXT_LEFT, pynk.lib.nk_vec2(120, 200)):
                    # static size_t prog = 40;
                    # static int slider = 10;
                    # static int check = nk_true;
                    # nk_layout_row_dynamic(ctx, 25, 1);
                    # if (nk_menu_item_label(ctx, "Hide", NK_TEXT_LEFT))
                    #     show_menu = nk_false;
                    # if (nk_menu_item_label(ctx, "About", NK_TEXT_LEFT))
                    #     show_app_about = nk_true;
                    # nk_progress(ctx, &prog, 100, NK_MODIFIABLE);
                    # nk_slider_int(ctx, 0, &slider, 16, 1);
                    # nk_checkbox_label(ctx, "check", &check);
                    # nk_menu_end(ctx);
                    self.declare("prog", 40, "unsigned int*")
                    self.declare("slider", 10, "int*")
                    self.declare("check", 1, "int*")
                    pynk.lib.nk_layout_row_dynamic(ctx, 25, 1)
                    if pynk.lib.nk_menu_item_label(ctx, "Hide", pynk.lib.NK_TEXT_LEFT):
                        self.show_menu = False;
                    if pynk.lib.nk_menu_item_label(ctx, "About", pynk.lib.NK_TEXT_LEFT):
                        self.show_app_about = True;
                    pynk.lib.nk_progress(ctx, self.prog, 100, pynk.lib.NK_MODIFIABLE)
                    pynk.lib.nk_slider_int(ctx, 0, self.slider, 16, 1)
                    pynk.lib.nk_checkbox_label(ctx, "check", self.check);
                    pynk.lib.nk_menu_end(ctx);

                # }
                # /* menu #2 */
                # nk_layout_row_push(ctx, 60);
                # if (nk_menu_begin_label(ctx, "ADVANCED", NK_TEXT_LEFT, nk_vec2(200, 600)))
                # {
                pynk.lib.nk_layout_row_push(ctx, 60);
                if pynk.lib.nk_menu_begin_label(ctx, "ADVANCED", pynk.lib.NK_TEXT_LEFT, pynk.lib.nk_vec2(200, 600)):
                    # enum menu_state {MENU_NONE,MENU_FILE, MENU_EDIT,MENU_VIEW,MENU_CHART};
                    # static enum menu_state menu_state = MENU_NONE;
                    # enum nk_collapse_states state;
                    MENU_NONE = 0
                    MENU_FILE = 1
                    MENU_EDIT = 2
                    MENU_VIEW = 3
                    MENU_CHART = 4
                    self.declare("menu_state", MENU_NONE)
                    state = pynk.ffi.new("enum nk_collapse_states*")

                    # state = (menu_state == MENU_FILE) ? NK_MAXIMIZED: NK_MINIMIZED;
                    # if (nk_tree_state_push(ctx, NK_TREE_TAB, "FILE", &state)) {
                    #     menu_state = MENU_FILE;
                    #     nk_menu_item_label(ctx, "New", NK_TEXT_LEFT);
                    #     nk_menu_item_label(ctx, "Open", NK_TEXT_LEFT);
                    #     nk_menu_item_label(ctx, "Save", NK_TEXT_LEFT);
                    #     nk_menu_item_label(ctx, "Close", NK_TEXT_LEFT);
                    #     nk_menu_item_label(ctx, "Exit", NK_TEXT_LEFT);
                    #     nk_tree_pop(ctx);
                    # } else menu_state = (menu_state == MENU_FILE) ? MENU_NONE: menu_state;
                    state[0] = pynk.lib.NK_MAXIMIZED if self.menu_state == MENU_FILE else pynk.lib.NK_MINIMIZED
                    if pynk.lib.nk_tree_state_push(ctx, pynk.lib.NK_TREE_TAB, "FILE", state):
                        self.menu_state = MENU_FILE
                        pynk.lib.nk_menu_item_label(ctx, "New", pynk.lib.NK_TEXT_LEFT)
                        pynk.lib.nk_menu_item_label(ctx, "Open", pynk.lib.NK_TEXT_LEFT)
                        pynk.lib.nk_menu_item_label(ctx, "Save", pynk.lib.NK_TEXT_LEFT)
                        pynk.lib.nk_menu_item_label(ctx, "Close", pynk.lib.NK_TEXT_LEFT)
                        pynk.lib.nk_menu_item_label(ctx, "Exit", pynk.lib.NK_TEXT_LEFT)
                        pynk.lib.nk_tree_pop(ctx)
                    elif self.menu_state == MENU_FILE:
                        self.menu_state = MENU_NONE

                    #
                    # state = (menu_state == MENU_EDIT) ? NK_MAXIMIZED: NK_MINIMIZED;
                    # if (nk_tree_state_push(ctx, NK_TREE_TAB, "EDIT", &state)) {
                    #     menu_state = MENU_EDIT;
                    #     nk_menu_item_label(ctx, "Copy", NK_TEXT_LEFT);
                    #     nk_menu_item_label(ctx, "Delete", NK_TEXT_LEFT);
                    #     nk_menu_item_label(ctx, "Cut", NK_TEXT_LEFT);
                    #     nk_menu_item_label(ctx, "Paste", NK_TEXT_LEFT);
                    #     nk_tree_pop(ctx);
                    # } else menu_state = (menu_state == MENU_EDIT) ? MENU_NONE: menu_state;
                    state[0] = pynk.lib.NK_MAXIMIZED if self.menu_state == MENU_EDIT else pynk.lib.NK_MINIMIZED
                    if pynk.lib.nk_tree_state_push(ctx, pynk.lib.NK_TREE_TAB, "EDIT", state):
                        self.menu_state = MENU_EDIT
                        pynk.lib.nk_menu_item_label(ctx, "Copy", pynk.lib.NK_TEXT_LEFT)
                        pynk.lib.nk_menu_item_label(ctx, "Delete", pynk.lib.NK_TEXT_LEFT)
                        pynk.lib.nk_menu_item_label(ctx, "Cut", pynk.lib.NK_TEXT_LEFT)
                        pynk.lib.nk_menu_item_label(ctx, "Paste", pynk.lib.NK_TEXT_LEFT)
                        pynk.lib.nk_tree_pop(ctx)
                    elif self.menu_state == MENU_EDIT:
                        self.menu_state = MENU_NONE

                    #
                    # state = (menu_state == MENU_VIEW) ? NK_MAXIMIZED: NK_MINIMIZED;
                    # if (nk_tree_state_push(ctx, NK_TREE_TAB, "VIEW", &state)) {
                    #     menu_state = MENU_VIEW;
                    #     nk_menu_item_label(ctx, "About", NK_TEXT_LEFT);
                    #     nk_menu_item_label(ctx, "Options", NK_TEXT_LEFT);
                    #     nk_menu_item_label(ctx, "Customize", NK_TEXT_LEFT);
                    #     nk_tree_pop(ctx);
                    # } else menu_state = (menu_state == MENU_VIEW) ? MENU_NONE: menu_state;
                    state[0] = pynk.lib.NK_MAXIMIZED if self.menu_state == MENU_VIEW else pynk.lib.NK_MINIMIZED
                    if pynk.lib.nk_tree_state_push(ctx, pynk.lib.NK_TREE_TAB, "VIEW", state):
                        self.menu_state = MENU_VIEW
                        pynk.lib.nk_menu_item_label(ctx, "About", pynk.lib.NK_TEXT_LEFT)
                        pynk.lib.nk_menu_item_label(ctx, "Options", pynk.lib.NK_TEXT_LEFT)
                        pynk.lib.nk_menu_item_label(ctx, "Customize", pynk.lib.NK_TEXT_LEFT)
                        pynk.lib.nk_tree_pop(ctx)
                    elif self.menu_state == MENU_VIEW:
                        self.menu_state = MENU_NONE

                    #
                    # state = (menu_state == MENU_CHART) ? NK_MAXIMIZED: NK_MINIMIZED;
                    # if (nk_tree_state_push(ctx, NK_TREE_TAB, "CHART", &state)) {
                    #     size_t i = 0;
                    #     const float values[]={26.0f,13.0f,30.0f,15.0f,25.0f,10.0f,20.0f,40.0f,12.0f,8.0f,22.0f,28.0f};
                    #     menu_state = MENU_CHART;
                    #     nk_layout_row_dynamic(ctx, 150, 1);
                    #     nk_chart_begin(ctx, NK_CHART_COLUMN, LEN(values), 0, 50);
                    #     for (i = 0; i < LEN(values); ++i)
                    #         nk_chart_push(ctx, values[i]);
                    #     nk_chart_end(ctx);
                    #     nk_tree_pop(ctx);
                    # } else menu_state = (menu_state == MENU_CHART) ? MENU_NONE: menu_state;
                    # nk_menu_end(ctx);
                    state[0] = pynk.lib.NK_MAXIMIZED if self.menu_state == MENU_CHART else pynk.lib.NK_MINIMIZED
                    if pynk.lib.nk_tree_state_push(ctx, pynk.lib.NK_TREE_TAB, "CHART", state):
                        self.menu_state = MENU_CHART
                        # size_t i = 0;
                        # const float values[]={26.0f,13.0f,30.0f,15.0f,25.0f,10.0f,20.0f,40.0f,12.0f,8.0f,22.0f,28.0f};
                        # nk_layout_row_dynamic(ctx, 150, 1);
                        # nk_chart_begin(ctx, NK_CHART_COLUMN, LEN(values), 0, 50);
                        # for (i = 0; i < LEN(values); ++i)
                        #     nk_chart_push(ctx, values[i]);
                        # nk_chart_end(ctx);
                        pynk.lib.nk_layout_row_dynamic(ctx, 150, 1)
                        values = [26.0,13.0,30.0,15.0,25.0,10.0,20.0,40.0,12.0,8.0,22.0,28.0]
                        pynk.lib.nk_chart_begin(ctx, pynk.lib.NK_CHART_COLUMN, len(values), 0, 50)
                        for value in values:
                            pynk.lib.nk_chart_push(ctx, value)
                        pynk.lib.nk_chart_end(ctx)
                        pynk.lib.nk_tree_pop(ctx)
                    elif self.menu_state == MENU_CHART:
                        self.menu_state = MENU_NONE
                    pynk.lib.nk_menu_end(ctx)
                # }
                # /* menu widgets */
                # nk_layout_row_push(ctx, 70);
                # nk_progress(ctx, &mprog, 100, NK_MODIFIABLE);
                # nk_slider_int(ctx, 0, &mslider, 16, 1);
                # nk_checkbox_label(ctx, "check", &mcheck);
                # nk_menubar_end(ctx);
                pynk.lib.nk_layout_row_push(ctx, 70)
                pynk.lib.nk_progress(ctx, self.mprog, 100, pynk.lib.NK_MODIFIABLE)
                pynk.lib.nk_slider_int(ctx, 0, self.mslider, 16, 1)
                pynk.lib.nk_checkbox_label(ctx, "check", self.mcheck)
                pynk.lib.nk_menubar_end(ctx);
            # }
            #
            # if (show_app_about)
            # {
            if self.show_app_about:
                # /* about popup */
                # static struct nk_rect s = {20, 100, 300, 190};
                # if (nk_popup_begin(ctx, NK_POPUP_STATIC, "About", NK_WINDOW_CLOSABLE, s))
                # {
                #     nk_layout_row_dynamic(ctx, 20, 1);
                #     nk_label(ctx, "Nuklear", NK_TEXT_LEFT);
                #     nk_label(ctx, "By Micha Mettke", NK_TEXT_LEFT);
                #     nk_label(ctx, "nuklear is licensed under the public domain License.",  NK_TEXT_LEFT);
                #     nk_popup_end(ctx);
                # } else show_app_about = nk_false;
                if pynk.lib.nk_popup_begin(ctx, pynk.lib.NK_POPUP_STATIC, "About", pynk.lib.NK_WINDOW_CLOSABLE, pynk.lib.nk_rect(20, 100, 300, 190)):
                    pynk.lib.nk_layout_row_dynamic(ctx, 20, 1);
                    pynk.lib.nk_label(ctx, "Nuklear", pynk.lib.NK_TEXT_LEFT);
                    pynk.lib.nk_label(ctx, "By Micha Mettke", pynk.lib.NK_TEXT_LEFT);
                    pynk.lib.nk_label(ctx, "nuklear is licensed under the public domain License.",  pynk.lib.NK_TEXT_LEFT);
                    pynk.lib.nk_popup_end(ctx);
                else: self.show_app_about = False;
            # }
            #
            # /* window flags */
            # if (nk_tree_push(ctx, NK_TREE_TAB, "Window", NK_MINIMIZED)) {
            #     nk_layout_row_dynamic(ctx, 30, 2);
            #     nk_checkbox_label(ctx, "Titlebar", &titlebar);
            #     nk_checkbox_label(ctx, "Menu", &show_menu);
            #     nk_checkbox_label(ctx, "Border", &border);
            #     nk_checkbox_label(ctx, "Resizable", &resize);
            #     nk_checkbox_label(ctx, "Movable", &movable);
            #     nk_checkbox_label(ctx, "No Scrollbar", &no_scrollbar);
            #     nk_checkbox_label(ctx, "Minimizable", &minimizable);
            #     nk_checkbox_label(ctx, "Scale Left", &scale_left);
            #     nk_tree_pop(ctx);
            # }
            if self.tree_push(ctx, pynk.lib.NK_TREE_TAB, "Window", pynk.lib.NK_MINIMIZED, "1"):
                pynk.lib.nk_layout_row_dynamic(ctx, 30, 2);
                pynk.lib.nk_checkbox_label(ctx, "Titlebar", self.titlebar);
                pynk.lib.nk_checkbox_label(ctx, "Menu", self.show_menu);
                pynk.lib.nk_checkbox_label(ctx, "Border", self.border);
                pynk.lib.nk_checkbox_label(ctx, "Resizable", self.resize);
                pynk.lib.nk_checkbox_label(ctx, "Movable", self.movable);
                pynk.lib.nk_checkbox_label(ctx, "No Scrollbar", self.no_scrollbar);
                pynk.lib.nk_checkbox_label(ctx, "Minimizable", self.minimizable);
                pynk.lib.nk_checkbox_label(ctx, "Scale Left", self.scale_left);
                pynk.lib.nk_tree_pop(ctx);

            #
            # if (nk_tree_push(ctx, NK_TREE_TAB, "Widgets", NK_MINIMIZED))
            # {
            #     enum options {A,B,C};
            #     static int checkbox;
            #     static int option;
            if self.tree_push(ctx, pynk.lib.NK_TREE_TAB, "Widgets", pynk.lib.NK_MINIMIZED, "2"):
                A = 0
                B = 1
                C = 2
                self.declare("checkbox", 0, "int*")
                self.declare("option", 0, "int*")

                # if (nk_tree_push(ctx, NK_TREE_NODE, "Text", NK_MINIMIZED))
                # {
                #     /* Text Widgets */
                #     nk_layout_row_dynamic(ctx, 20, 1);
                #     nk_label(ctx, "Label aligned left", NK_TEXT_LEFT);
                #     nk_label(ctx, "Label aligned centered", NK_TEXT_CENTERED);
                #     nk_label(ctx, "Label aligned right", NK_TEXT_RIGHT);
                #     nk_label_colored(ctx, "Blue text", NK_TEXT_LEFT, nk_rgb(0,0,255));
                #     nk_label_colored(ctx, "Yellow text", NK_TEXT_LEFT, nk_rgb(255,255,0));
                #     nk_text(ctx, "Text without /0", 15, NK_TEXT_RIGHT);
                #
                #     nk_layout_row_static(ctx, 100, 200, 1);
                #     nk_label_wrap(ctx, "This is a very long line to hopefully get this text to be wrapped into multiple lines to show line wrapping");
                #     nk_layout_row_dynamic(ctx, 100, 1);
                #     nk_label_wrap(ctx, "This is another long text to show dynamic window changes on multiline text");
                #     nk_tree_pop(ctx);
                # }
                if self.tree_push(ctx, pynk.lib.NK_TREE_NODE, "Text", pynk.lib.NK_MINIMIZED, "3"):
                    pynk.lib.nk_layout_row_dynamic(ctx, 20, 1);
                    pynk.lib.nk_label(ctx, "Label aligned left", pynk.lib.NK_TEXT_LEFT);
                    pynk.lib.nk_label(ctx, "Label aligned centered", pynk.lib.NK_TEXT_CENTERED);
                    pynk.lib.nk_label(ctx, "Label aligned right", pynk.lib.NK_TEXT_RIGHT);
                    pynk.lib.nk_label_colored(ctx, "Blue text", pynk.lib.NK_TEXT_LEFT, pynk.lib.nk_rgb(0,0,255));
                    pynk.lib.nk_label_colored(ctx, "Yellow text", pynk.lib.NK_TEXT_LEFT, pynk.lib.nk_rgb(255,255,0));
                    pynk.lib.nk_text(ctx, "Text without /0", 15, pynk.lib.NK_TEXT_RIGHT);
                    pynk.lib.nk_layout_row_static(ctx, 100, 200, 1);
                    pynk.lib.nk_label_wrap(ctx, "This is a very long line to hopefully get this text to be wrapped into multiple lines to show line wrapping");
                    pynk.lib.nk_layout_row_dynamic(ctx, 100, 1);
                    pynk.lib.nk_label_wrap(ctx, "This is another long text to show dynamic window changes on multiline text");
                    pynk.lib.nk_tree_pop(ctx);
                #
                # if (nk_tree_push(ctx, NK_TREE_NODE, "Button", NK_MINIMIZED))
                # {
                #     /* Buttons Widgets */
                #     nk_layout_row_static(ctx, 30, 100, 3);
                #     if (nk_button_label(ctx, "Button"))
                #         fprintf(stdout, "Button pressed!\n");
                #     nk_button_set_behavior(ctx, NK_BUTTON_REPEATER);
                #     if (nk_button_label(ctx, "Repeater"))
                #         fprintf(stdout, "Repeater is being pressed!\n");
                #     nk_button_set_behavior(ctx, NK_BUTTON_DEFAULT);
                #     nk_button_color(ctx, nk_rgb(0,0,255));
                #
                #     nk_layout_row_static(ctx, 25, 25, 8);
                #     nk_button_symbol(ctx, NK_SYMBOL_CIRCLE_SOLID);
                #     nk_button_symbol(ctx, NK_SYMBOL_CIRCLE_OUTLINE);
                #     nk_button_symbol(ctx, NK_SYMBOL_RECT_SOLID);
                #     nk_button_symbol(ctx, NK_SYMBOL_RECT_OUTLINE);
                #     nk_button_symbol(ctx, NK_SYMBOL_TRIANGLE_UP);
                #     nk_button_symbol(ctx, NK_SYMBOL_TRIANGLE_DOWN);
                #     nk_button_symbol(ctx, NK_SYMBOL_TRIANGLE_LEFT);
                #     nk_button_symbol(ctx, NK_SYMBOL_TRIANGLE_RIGHT);
                #
                #     nk_layout_row_static(ctx, 30, 100, 2);
                #     nk_button_symbol_label(ctx, NK_SYMBOL_TRIANGLE_LEFT, "prev", NK_TEXT_RIGHT);
                #     nk_button_symbol_label(ctx, NK_SYMBOL_TRIANGLE_RIGHT, "next", NK_TEXT_LEFT);
                #     nk_tree_pop(ctx);
                # }
                if self.tree_push(ctx, pynk.lib.NK_TREE_NODE, "Button", pynk.lib.NK_MINIMIZED, "4"):
                    pynk.lib.nk_layout_row_static(ctx, 30, 100, 3);
                    if pynk.lib.nk_button_label(ctx, "Button"):
                        print "Button pressed!"
                    pynk.lib.nk_button_set_behavior(ctx, pynk.lib.NK_BUTTON_REPEATER);
                    if pynk.lib.nk_button_label(ctx, "Repeater"):
                        print "Repeater is being pressed!"
                    pynk.lib.nk_button_set_behavior(ctx, pynk.lib.NK_BUTTON_DEFAULT);
                    pynk.lib.nk_button_color(ctx, pynk.lib.nk_rgb(0,0,255));
                    pynk.lib.nk_layout_row_static(ctx, 25, 25, 8);
                    pynk.lib.nk_button_symbol(ctx, pynk.lib.NK_SYMBOL_CIRCLE_SOLID);
                    pynk.lib.nk_button_symbol(ctx, pynk.lib.NK_SYMBOL_CIRCLE_OUTLINE);
                    pynk.lib.nk_button_symbol(ctx, pynk.lib.NK_SYMBOL_RECT_SOLID);
                    pynk.lib.nk_button_symbol(ctx, pynk.lib.NK_SYMBOL_RECT_OUTLINE);
                    pynk.lib.nk_button_symbol(ctx, pynk.lib.NK_SYMBOL_TRIANGLE_UP);
                    pynk.lib.nk_button_symbol(ctx, pynk.lib.NK_SYMBOL_TRIANGLE_DOWN);
                    pynk.lib.nk_button_symbol(ctx, pynk.lib.NK_SYMBOL_TRIANGLE_LEFT);
                    pynk.lib.nk_button_symbol(ctx, pynk.lib.NK_SYMBOL_TRIANGLE_RIGHT);
                    pynk.lib.nk_layout_row_static(ctx, 30, 100, 2);
                    pynk.lib.nk_button_symbol_label(ctx, pynk.lib.NK_SYMBOL_TRIANGLE_LEFT, "prev", pynk.lib.NK_TEXT_RIGHT);
                    pynk.lib.nk_button_symbol_label(ctx, pynk.lib.NK_SYMBOL_TRIANGLE_RIGHT, "next", pynk.lib.NK_TEXT_LEFT);
                    pynk.lib.nk_tree_pop(ctx);
                #
                # if (nk_tree_push(ctx, NK_TREE_NODE, "Basic", NK_MINIMIZED))
                # {
                #     /* Basic widgets */
                #     static int int_slider = 5;
                #     static float float_slider = 2.5f;
                #     static size_t prog_value = 40;
                #     static float property_float = 2;
                #     static int property_int = 10;
                #     static int property_neg = 10;
                #
                #     static float range_float_min = 0;
                #     static float range_float_max = 100;
                #     static float range_float_value = 50;
                #     static int range_int_min = 0;
                #     static int range_int_value = 2048;
                #     static int range_int_max = 4096;
                #     static const float ratio[] = {120, 150};
                #
                #     nk_layout_row_static(ctx, 30, 100, 1);
                #     nk_checkbox_label(ctx, "Checkbox", &checkbox);
                #
                #     nk_layout_row_static(ctx, 30, 80, 3);
                #     option = nk_option_label(ctx, "optionA", option == A) ? A : option;
                #     option = nk_option_label(ctx, "optionB", option == B) ? B : option;
                #     option = nk_option_label(ctx, "optionC", option == C) ? C : option;
                #
                #
                #     nk_layout_row(ctx, NK_STATIC, 30, 2, ratio);
                #     nk_labelf(ctx, NK_TEXT_LEFT, "Slider int");
                #     nk_slider_int(ctx, 0, &int_slider, 10, 1);
                #
                #     nk_label(ctx, "Slider float", NK_TEXT_LEFT);
                #     nk_slider_float(ctx, 0, &float_slider, 5.0, 0.5f);
                #     nk_labelf(ctx, NK_TEXT_LEFT, "Progressbar" , prog_value);
                #     nk_progress(ctx, &prog_value, 100, NK_MODIFIABLE);
                #
                #     nk_layout_row(ctx, NK_STATIC, 25, 2, ratio);
                #     nk_label(ctx, "Property float:", NK_TEXT_LEFT);
                #     nk_property_float(ctx, "Float:", 0, &property_float, 64.0f, 0.1f, 0.2f);
                #     nk_label(ctx, "Property int:", NK_TEXT_LEFT);
                #     nk_property_int(ctx, "Int:", 0, &property_int, 100.0f, 1, 1);
                #     nk_label(ctx, "Property neg:", NK_TEXT_LEFT);
                #     nk_property_int(ctx, "Neg:", -10, &property_neg, 10, 1, 1);
                #
                #     nk_layout_row_dynamic(ctx, 25, 1);
                #     nk_label(ctx, "Range:", NK_TEXT_LEFT);
                #     nk_layout_row_dynamic(ctx, 25, 3);
                #     nk_property_float(ctx, "#min:", 0, &range_float_min, range_float_max, 1.0f, 0.2f);
                #     nk_property_float(ctx, "#float:", range_float_min, &range_float_value, range_float_max, 1.0f, 0.2f);
                #     nk_property_float(ctx, "#max:", range_float_min, &range_float_max, 100, 1.0f, 0.2f);
                #
                #     nk_property_int(ctx, "#min:", INT_MIN, &range_int_min, range_int_max, 1, 10);
                #     nk_property_int(ctx, "#neg:", range_int_min, &range_int_value, range_int_max, 1, 10);
                #     nk_property_int(ctx, "#max:", range_int_min, &range_int_max, INT_MAX, 1, 10);
                #
                #     nk_tree_pop(ctx);
                # }
                if self.tree_push(ctx, pynk.lib.NK_TREE_NODE, "Basic", pynk.lib.NK_MINIMIZED, "5"):
                    self.declare("int_slider", 5, "int*")
                    self.declare("float_slider", 2.5, "float*")
                    self.declare("prog_value", 40, "unsigned int*")
                    self.declare("property_float", 2, "float*")
                    self.declare("property_int", 10, "int*")
                    self.declare("property_neg", 10, "int*")
                    self.declare("range_float_min", 0, "float*")
                    self.declare("range_float_max", 100, "float*")
                    self.declare("range_float_value", 50, "float*")
                    self.declare("range_int_min", 0, "int*")
                    self.declare("range_int_value", 2048, "int*")
                    self.declare("range_int_max", 4096, "int*")
                    self.declare("ratio", [120, 150], "float[]")

                    pynk.lib.nk_layout_row_static(ctx, 30, 100, 1)
                    pynk.lib.nk_checkbox_label(ctx, "Checkbox", self.checkbox)

                    pynk.lib.nk_layout_row_static(ctx, 30, 80, 3)
                    if pynk.lib.nk_option_label(ctx, "optionA", self.option[0] == A):
                        self.option[0] = A
                    if pynk.lib.nk_option_label(ctx, "optionB", self.option[0] == B):
                        self.option[0] = B
                    if pynk.lib.nk_option_label(ctx, "optionC", self.option[0] == C):
                        self.option[0] = C

                    pynk.lib.nk_layout_row(ctx, pynk.lib.NK_STATIC, 30, 2, self.ratio);
                    pynk.lib.nk_labelf(ctx, pynk.lib.NK_TEXT_LEFT, "Slider int");
                    pynk.lib.nk_slider_int(ctx, 0, self.int_slider, 10, 1)

                    pynk.lib.nk_label(ctx, "Slider float", pynk.lib.NK_TEXT_LEFT);
                    pynk.lib.nk_slider_float(ctx, 0, self.float_slider, 5.0, 0.5)
                    pynk.lib.nk_labelf(ctx, pynk.lib.NK_TEXT_LEFT, "Progressbar" , self.prog_value);
                    pynk.lib.nk_progress(ctx, self.prog_value, 100, pynk.lib.NK_MODIFIABLE)

                    pynk.lib.nk_layout_row(ctx, pynk.lib.NK_STATIC, 25, 2, self.ratio);
                    pynk.lib.nk_label(ctx, "Property float:", pynk.lib.NK_TEXT_LEFT);
                    pynk.lib.nk_property_float(ctx, "Float:", 0, self.property_float, 64.0, 0.1, 0.2);
                    pynk.lib.nk_label(ctx, "Property int:", pynk.lib.NK_TEXT_LEFT);
                    pynk.lib.nk_property_int(ctx, "Int:", 0, self.property_int, 100, 1, 1)
                    pynk.lib.nk_label(ctx, "Property neg:", pynk.lib.NK_TEXT_LEFT);
                    pynk.lib.nk_property_int(ctx, "Neg:", -10, self.property_neg, 10, 1, 1)

                    pynk.lib.nk_layout_row_dynamic(ctx, 25, 1);
                    pynk.lib.nk_label(ctx, "Range:", pynk.lib.NK_TEXT_LEFT);
                    pynk.lib.nk_layout_row_dynamic(ctx, 25, 3);
                    pynk.lib.nk_property_float(ctx, "#min:", 0, self.range_float_min, self.range_float_max[0], 1.0, 0.2);
                    pynk.lib.nk_property_float(ctx, "#float:", self.range_float_min[0], self.range_float_value, self.range_float_max[0], 1.0, 0.2);
                    pynk.lib.nk_property_float(ctx, "#max:", self.range_float_min[0], self.range_float_max, 100, 1.0, 0.2);

                    pynk.lib.nk_property_int(ctx, "#min:", INT_MIN, self.range_int_min, self.range_int_max[0], 1, 10);
                    pynk.lib.nk_property_int(ctx, "#neg:", self.range_int_min[0], self.range_int_value, self.range_int_max[0], 1, 10);
                    pynk.lib.nk_property_int(ctx, "#max:", self.range_int_min[0], self.range_int_max, INT_MAX, 1, 10);

                    pynk.lib.nk_tree_pop(ctx);
                #
                # if (nk_tree_push(ctx, NK_TREE_NODE, "Selectable", NK_MINIMIZED))
                # {
                #     if (nk_tree_push(ctx, NK_TREE_NODE, "List", NK_MINIMIZED))
                #     {
                #         static int selected[4] = {nk_false, nk_false, nk_true, nk_false};
                #         nk_layout_row_static(ctx, 18, 100, 1);
                #         nk_selectable_label(ctx, "Selectable", NK_TEXT_LEFT, &selected[0]);
                #         nk_selectable_label(ctx, "Selectable", NK_TEXT_LEFT, &selected[1]);
                #         nk_label(ctx, "Not Selectable", NK_TEXT_LEFT);
                #         nk_selectable_label(ctx, "Selectable", NK_TEXT_LEFT, &selected[2]);
                #         nk_selectable_label(ctx, "Selectable", NK_TEXT_LEFT, &selected[3]);
                #         nk_tree_pop(ctx);
                #     }
                #     if (nk_tree_push(ctx, NK_TREE_NODE, "Grid", NK_MINIMIZED))
                #     {
                #         int i;
                #         static int selected[16] = {1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1};
                #         nk_layout_row_static(ctx, 50, 50, 4);
                #         for (i = 0; i < 16; ++i) {
                #             if (nk_selectable_label(ctx, "Z", NK_TEXT_CENTERED, &selected[i])) {
                #                 int x = (i % 4), y = i / 4;
                #                 if (x > 0) selected[i - 1] ^= 1;
                #                 if (x < 3) selected[i + 1] ^= 1;
                #                 if (y > 0) selected[i - 4] ^= 1;
                #                 if (y < 3) selected[i + 4] ^= 1;
                #             }
                #         }
                #         nk_tree_pop(ctx);
                #     }
                #     nk_tree_pop(ctx);
                # }
                if self.tree_push(ctx, pynk.lib.NK_TREE_NODE, "Selectable", pynk.lib.NK_MINIMIZED, "6"):
                    if self.tree_push(ctx, pynk.lib.NK_TREE_NODE, "List", pynk.lib.NK_MINIMIZED, "7"):
                        self.declare("selected1", [0, 0, 1, 0], "int[]")
                        pynk.lib.nk_layout_row_static(ctx, 18, 100, 1);
                        pynk.lib.nk_selectable_label(ctx, "Selectable", pynk.lib.NK_TEXT_LEFT, self.selected1+0);
                        pynk.lib.nk_selectable_label(ctx, "Selectable", pynk.lib.NK_TEXT_LEFT, self.selected1+1);
                        pynk.lib.nk_label(ctx, "Not Selectable", pynk.lib.NK_TEXT_LEFT);
                        pynk.lib.nk_selectable_label(ctx, "Selectable", pynk.lib.NK_TEXT_LEFT, self.selected1+2);
                        pynk.lib.nk_selectable_label(ctx, "Selectable", pynk.lib.NK_TEXT_LEFT, self.selected1+3);
                        pynk.lib.nk_tree_pop(ctx);
                    if self.tree_push(ctx, pynk.lib.NK_TREE_NODE, "Grid", pynk.lib.NK_MINIMIZED, "8"):
                        self.declare("selected2", [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1], "int[]")
                        pynk.lib.nk_layout_row_static(ctx, 50, 50, 4);
                        for i in xrange(len(self.selected2)):
                            if pynk.lib.nk_selectable_label(ctx, "Z", pynk.lib.NK_TEXT_CENTERED, self.selected2+i):
                                x = i % 4
                                y = i / 4
                                if x > 0: self.selected2[i - 1] ^= 1;
                                if x < 3: self.selected2[i + 1] ^= 1;
                                if y > 0: self.selected2[i - 4] ^= 1;
                                if y < 3: self.selected2[i + 4] ^= 1;
                        pynk.lib.nk_tree_pop(ctx);
                    pynk.lib.nk_tree_pop(ctx);
                #
                # if (nk_tree_push(ctx, NK_TREE_NODE, "Combo", NK_MINIMIZED))
                # {
                #     /* Combobox Widgets
                #      * In this library comboboxes are not limited to being a popup
                #      * list of selectable text. Instead it is a abstract concept of
                #      * having something that is *selected* or displayed, a popup window
                #      * which opens if something needs to be modified and the content
                #      * of the popup which causes the *selected* or displayed value to
                #      * change or if wanted close the combobox.
                #      *
                #      * While strange at first handling comboboxes in a abstract way
                #      * solves the problem of overloaded window content. For example
                #      * changing a color value requires 4 value modifier (slider, property,...)
                #      * for RGBA then you need a label and ways to display the current color.
                #      * If you want to go fancy you even add rgb and hsv ratio boxes.
                #      * While fine for one color if you have a lot of them it because
                #      * tedious to look at and quite wasteful in space. You could add
                #      * a popup which modifies the color but this does not solve the
                #      * fact that it still requires a lot of cluttered space to do.
                #      *
                #      * In these kind of instance abstract comboboxes are quite handy. All
                #      * value modifiers are hidden inside the combobox popup and only
                #      * the color is shown if not open. This combines the clarity of the
                #      * popup with the ease of use of just using the space for modifiers.
                #      *
                #      * Other instances are for example time and especially date picker,
                #      * which only show the currently activated time/data and hide the
                #      * selection logic inside the combobox popup.
                #      */
                if self.tree_push(ctx, pynk.lib.NK_TREE_NODE, "Combo", pynk.lib.NK_MINIMIZED, "9"):
                    # static float chart_selection = 8.0f;
                    # static int current_weapon = 0;
                    # static int check_values[5];
                    # static float position[3];
                    # static struct nk_color combo_color = {130, 50, 50, 255};
                    # static struct nk_color combo_color2 = {130, 180, 50, 255};
                    # static size_t prog_a =  20, prog_b = 40, prog_c = 10, prog_d = 90;
                    # static const char *weapons[] = {"Fist","Pistol","Shotgun","Plasma","BFG"};
                    #
                    # char buffer[64];
                    # size_t sum = 0;
                    self.declare("chart_selection", 8.0, "float*")
                    self.declare("current_weapon", 0, "int*")
                    self.declare("check_values", [0, 0, 0, 0, 0], "int[]")
                    self.declare("position", [0, 0, 0], "float[]")
                    self.declare("combo_color", [130, 50, 50, 255], "struct nk_color*")
                    self.declare("combo_color2", [130, 180, 50, 255], "struct nk_color*")
                    self.declare("prog_a", 20, "unsigned int*")
                    self.declare("prog_b", 40, "unsigned int*")
                    self.declare("prog_c", 10, "unsigned int*")
                    self.declare("prog_d", 90, "unsigned int*")
                    self.declare_string_array("weapons", ["Fist", "Pistol", "Shotgun", "Plasma", "BFG"])
                    #
                    # /* default combobox */
                    # nk_layout_row_static(ctx, 25, 200, 1);
                    # current_weapon = nk_combo(ctx, weapons, LEN(weapons), current_weapon, 25, nk_vec2(200,200));
                    pynk.lib.nk_layout_row_static(ctx, 25, 200, 1);
                    self.current_weapon[0] = pynk.lib.nk_combo(ctx, self.weapons, len(self.weapons), self.current_weapon[0], 25, pynk.lib.nk_vec2(200,200))

                    #
                    # /* slider color combobox */
                    # if (nk_combo_begin_color(ctx, combo_color, nk_vec2(200,200))) {
                    #     float ratios[] = {0.15f, 0.85f};
                    #     nk_layout_row(ctx, NK_DYNAMIC, 30, 2, ratios);
                    #     nk_label(ctx, "R:", NK_TEXT_LEFT);
                    #     combo_color.r = (nk_byte)nk_slide_int(ctx, 0, combo_color.r, 255, 5);
                    #     nk_label(ctx, "G:", NK_TEXT_LEFT);
                    #     combo_color.g = (nk_byte)nk_slide_int(ctx, 0, combo_color.g, 255, 5);
                    #     nk_label(ctx, "B:", NK_TEXT_LEFT);
                    #     combo_color.b = (nk_byte)nk_slide_int(ctx, 0, combo_color.b, 255, 5);
                    #     nk_label(ctx, "A:", NK_TEXT_LEFT);
                    #     combo_color.a = (nk_byte)nk_slide_int(ctx, 0, combo_color.a , 255, 5);
                    #     nk_combo_end(ctx);
                    # }
                    if pynk.lib.nk_combo_begin_color(ctx, self.combo_color[0], pynk.lib.nk_vec2(200,200)):
                        ratios = pynk.ffi.new("float[2]", [0.15, 0.85])
                        pynk.lib.nk_layout_row(ctx, pynk.lib.NK_DYNAMIC, 30, 2, ratios)
                        pynk.lib.nk_label(ctx, "R:", pynk.lib.NK_TEXT_LEFT)
                        self.combo_color.r = pynk.lib.nk_slide_int(ctx, 0, self.combo_color.r, 255, 5)
                        pynk.lib.nk_label(ctx, "G:", pynk.lib.NK_TEXT_LEFT)
                        self.combo_color.g = pynk.lib.nk_slide_int(ctx, 0, self.combo_color.g, 255, 5)
                        pynk.lib.nk_label(ctx, "B:", pynk.lib.NK_TEXT_LEFT)
                        self.combo_color.b = pynk.lib.nk_slide_int(ctx, 0, self.combo_color.b, 255, 5)
                        pynk.lib.nk_label(ctx, "A:", pynk.lib.NK_TEXT_LEFT)
                        self.combo_color.a = pynk.lib.nk_slide_int(ctx, 0, self.combo_color.a , 255, 5)
                        pynk.lib.nk_combo_end(ctx);
                    #
                    # /* complex color combobox */
                    # if (nk_combo_begin_color(ctx, combo_color2, nk_vec2(200,400))) {
                    #     enum color_mode {COL_RGB, COL_HSV};
                    #     static int col_mode = COL_RGB;
                    #     #ifndef DEMO_DO_NOT_USE_COLOR_PICKER
                    #     nk_layout_row_dynamic(ctx, 120, 1);
                    #     combo_color2 = nk_color_picker(ctx, combo_color2, NK_RGBA);
                    #     #endif
                    #
                    #     nk_layout_row_dynamic(ctx, 25, 2);
                    #     col_mode = nk_option_label(ctx, "RGB", col_mode == COL_RGB) ? COL_RGB : col_mode;
                    #     col_mode = nk_option_label(ctx, "HSV", col_mode == COL_HSV) ? COL_HSV : col_mode;
                    #
                    #     nk_layout_row_dynamic(ctx, 25, 1);
                    #     if (col_mode == COL_RGB) {
                    #         combo_color2.r = (nk_byte)nk_propertyi(ctx, "#R:", 0, combo_color2.r, 255, 1,1);
                    #         combo_color2.g = (nk_byte)nk_propertyi(ctx, "#G:", 0, combo_color2.g, 255, 1,1);
                    #         combo_color2.b = (nk_byte)nk_propertyi(ctx, "#B:", 0, combo_color2.b, 255, 1,1);
                    #         combo_color2.a = (nk_byte)nk_propertyi(ctx, "#A:", 0, combo_color2.a, 255, 1,1);
                    #     } else {
                    #         nk_byte tmp[4];
                    #         nk_color_hsva_bv(tmp, combo_color2);
                    #         tmp[0] = (nk_byte)nk_propertyi(ctx, "#H:", 0, tmp[0], 255, 1,1);
                    #         tmp[1] = (nk_byte)nk_propertyi(ctx, "#S:", 0, tmp[1], 255, 1,1);
                    #         tmp[2] = (nk_byte)nk_propertyi(ctx, "#V:", 0, tmp[2], 255, 1,1);
                    #         tmp[3] = (nk_byte)nk_propertyi(ctx, "#A:", 0, tmp[3], 255, 1,1);
                    #         combo_color2 = nk_hsva_bv(tmp);
                    #     }
                    #     nk_combo_end(ctx);
                    # }
                    if pynk.lib.nk_combo_begin_color(ctx, self.combo_color2[0], pynk.lib.nk_vec2(200,400)):
                        COL_RGB = 0
                        COL_HSV = 1
                        self.declare("col_mode", COL_RGB, "int*")
                        pynk.lib.nk_layout_row_dynamic(ctx, 120, 1);
                        self.combo_color2[0] = pynk.lib.nk_color_picker(ctx, self.combo_color2[0], pynk.lib.NK_RGBA);

                        pynk.lib.nk_layout_row_dynamic(ctx, 25, 2);
                        if pynk.lib.nk_option_label(ctx, "RGB", self.col_mode[0] == COL_RGB):
                            self.col_mode[0] = COL_RGB
                        if pynk.lib.nk_option_label(ctx, "HSV", self.col_mode[0] == COL_HSV):
                            self.col_mode[0] = COL_HSV

                        pynk.lib.nk_layout_row_dynamic(ctx, 25, 1);
                        if self.col_mode[0] == COL_RGB:
                            self.combo_color2.r = pynk.lib.nk_propertyi(ctx, "#R:", 0, self.combo_color2.r, 255, 1,1);
                            self.combo_color2.g = pynk.lib.nk_propertyi(ctx, "#G:", 0, self.combo_color2.g, 255, 1,1);
                            self.combo_color2.b = pynk.lib.nk_propertyi(ctx, "#B:", 0, self.combo_color2.b, 255, 1,1);
                            self.combo_color2.a = pynk.lib.nk_propertyi(ctx, "#A:", 0, self.combo_color2.a, 255, 1,1);
                        else:
                            tmp = pynk.ffi.new("nk_byte[4]")
                            pynk.lib.nk_color_hsva_bv(tmp, self.combo_color2[0]);
                            tmp[0] = pynk.lib.nk_propertyi(ctx, "#H:", 0, tmp[0], 255, 1,1);
                            tmp[1] = pynk.lib.nk_propertyi(ctx, "#S:", 0, tmp[1], 255, 1,1);
                            tmp[2] = pynk.lib.nk_propertyi(ctx, "#V:", 0, tmp[2], 255, 1,1);
                            tmp[3] = pynk.lib.nk_propertyi(ctx, "#A:", 0, tmp[3], 255, 1,1);
                            self.combo_color2[0] = pynk.lib.nk_hsva_bv(tmp);
                        pynk.lib.nk_combo_end(ctx);
                    #
                    # /* progressbar combobox */
                    # sum = prog_a + prog_b + prog_c + prog_d;
                    # sprintf(buffer, "%lu", sum);
                    # if (nk_combo_begin_label(ctx, buffer, nk_vec2(200,200))) {
                    #     nk_layout_row_dynamic(ctx, 30, 1);
                    #     nk_progress(ctx, &prog_a, 100, NK_MODIFIABLE);
                    #     nk_progress(ctx, &prog_b, 100, NK_MODIFIABLE);
                    #     nk_progress(ctx, &prog_c, 100, NK_MODIFIABLE);
                    #     nk_progress(ctx, &prog_d, 100, NK_MODIFIABLE);
                    #     nk_combo_end(ctx);
                    # }
                    prog_sum = self.prog_a[0] + self.prog_b[0] + self.prog_c[0] + self.prog_d[0]
                    if pynk.lib.nk_combo_begin_label(ctx, str(prog_sum), pynk.lib.nk_vec2(200,200)):
                        pynk.lib.nk_layout_row_dynamic(ctx, 30, 1);
                        pynk.lib.nk_progress(ctx, self.prog_a, 100, pynk.lib.NK_MODIFIABLE);
                        pynk.lib.nk_progress(ctx, self.prog_b, 100, pynk.lib.NK_MODIFIABLE);
                        pynk.lib.nk_progress(ctx, self.prog_c, 100, pynk.lib.NK_MODIFIABLE);
                        pynk.lib.nk_progress(ctx, self.prog_d, 100, pynk.lib.NK_MODIFIABLE);
                        pynk.lib.nk_combo_end(ctx);
                    #
                    # /* checkbox combobox */
                    # sum = (size_t)(check_values[0] + check_values[1] + check_values[2] + check_values[3] + check_values[4]);
                    # sprintf(buffer, "%lu", sum);
                    # if (nk_combo_begin_label(ctx, buffer, nk_vec2(200,200))) {
                    #     nk_layout_row_dynamic(ctx, 30, 1);
                    #     nk_checkbox_label(ctx, weapons[0], &check_values[0]);
                    #     nk_checkbox_label(ctx, weapons[1], &check_values[1]);
                    #     nk_checkbox_label(ctx, weapons[2], &check_values[2]);
                    #     nk_checkbox_label(ctx, weapons[3], &check_values[3]);
                    #     nk_combo_end(ctx);
                    # }
                    val_sum = self.check_values[0] + self.check_values[1] + self.check_values[2] + self.check_values[3] + self.check_values[4]
                    if pynk.lib.nk_combo_begin_label(ctx, str(val_sum), pynk.lib.nk_vec2(200,200)):
                        pynk.lib.nk_layout_row_dynamic(ctx, 30, 1);
                        pynk.lib.nk_checkbox_label(ctx, self.weapons[0], self.check_values);
                        pynk.lib.nk_checkbox_label(ctx, self.weapons[1], self.check_values+1);
                        pynk.lib.nk_checkbox_label(ctx, self.weapons[2], self.check_values+2);
                        pynk.lib.nk_checkbox_label(ctx, self.weapons[3], self.check_values+3);
                        pynk.lib.nk_combo_end(ctx);
                    #
                    # /* complex text combobox */
                    # sprintf(buffer, "%.2f, %.2f, %.2f", position[0], position[1],position[2]);
                    # if (nk_combo_begin_label(ctx, buffer, nk_vec2(200,200))) {
                    #     nk_layout_row_dynamic(ctx, 25, 1);
                    #     nk_property_float(ctx, "#X:", -1024.0f, &position[0], 1024.0f, 1,0.5f);
                    #     nk_property_float(ctx, "#Y:", -1024.0f, &position[1], 1024.0f, 1,0.5f);
                    #     nk_property_float(ctx, "#Z:", -1024.0f, &position[2], 1024.0f, 1,0.5f);
                    #     nk_combo_end(ctx);
                    # }
                    lab = "%s, %s, %s" % (self.position[0], self.position[1], self.position[2])
                    if pynk.lib.nk_combo_begin_label(ctx, lab, pynk.lib.nk_vec2(200,200)):
                        pynk.lib.nk_layout_row_dynamic(ctx, 25, 1);
                        pynk.lib.nk_property_float(ctx, "#X:", -1024.0, self.position, 1024.0, 1,0.5);
                        pynk.lib.nk_property_float(ctx, "#Y:", -1024.0, self.position+1, 1024.0, 1,0.5);
                        pynk.lib.nk_property_float(ctx, "#Z:", -1024.0, self.position+2, 1024.0, 1,0.5);
                        pynk.lib.nk_combo_end(ctx);
                    #
                    # /* chart combobox */
                    # sprintf(buffer, "%.1f", chart_selection);
                    # if (nk_combo_begin_label(ctx, buffer, nk_vec2(200,250))) {
                    #     size_t i = 0;
                    #     static const float values[]={26.0f,13.0f,30.0f,15.0f,25.0f,10.0f,20.0f,40.0f, 12.0f, 8.0f, 22.0f, 28.0f, 5.0f};
                    #     nk_layout_row_dynamic(ctx, 150, 1);
                    #     nk_chart_begin(ctx, NK_CHART_COLUMN, LEN(values), 0, 50);
                    #     for (i = 0; i < LEN(values); ++i) {
                    #         nk_flags res = nk_chart_push(ctx, values[i]);
                    #         if (res & NK_CHART_CLICKED) {
                    #             chart_selection = values[i];
                    #             nk_combo_close(ctx);
                    #         }
                    #     }
                    #     nk_chart_end(ctx);
                    #     nk_combo_end(ctx);
                    # }
                    if pynk.lib.nk_combo_begin_label(ctx, str(self.chart_selection[0]), pynk.lib.nk_vec2(200,250)):
                        values = [26.0,13.0,30.0,15.0,25.0,10.0,20.0,40.0, 12.0, 8.0, 22.0, 28.0, 5.0]
                        pynk.lib.nk_layout_row_dynamic(ctx, 150, 1);
                        pynk.lib.nk_chart_begin(ctx, pynk.lib.NK_CHART_COLUMN, len(values), 0, 50);
                        for i in xrange(len(values)):
                            res = pynk.lib.nk_chart_push(ctx, values[i]);
                            if res & pynk.lib.NK_CHART_CLICKED:
                                self.chart_selection[0] = values[i];
                                pynk.lib.nk_combo_close(ctx);
                        pynk.lib.nk_chart_end(ctx);
                        pynk.lib.nk_combo_end(ctx);

                    #static int time_selected = 0;
                    #static int date_selected = 0;
                    #static struct tm sel_time;
                    #static struct tm sel_date;
                    #if (!time_selected || !date_selected) {
                    #    /* keep time and date updated if nothing is selected */
                    #    time_t cur_time = time(0);
                    #    struct tm *n = localtime(&cur_time);
                    #    if (!time_selected)
                    #        memcpy(&sel_time, n, sizeof(struct tm));
                    #    if (!date_selected)
                    #        memcpy(&sel_date, n, sizeof(struct tm));
                    #}
                    self.declare("time_selected", False)
                    self.declare("date_selected", False)
                    self.declare("sel_time", None)
                    self.declare("sel_date", None)
                    cur_time = datetime.datetime.now()
                    if not self.time_selected:
                        self.sel_time = cur_time
                    if not self.date_selected:
                        self.sel_date = cur_time
                    #
                    #/* time combobox */
                    #sprintf(buffer, "%02d:%02d:%02d", sel_time.tm_hour, sel_time.tm_min, sel_time.tm_sec);
                    sel_time_str = self.sel_time.strftime("%H:%M:%S")
                    #if (nk_combo_begin_label(ctx, buffer, nk_vec2(200,250))) {
                    #    time_selected = 1;
                    #    nk_layout_row_dynamic(ctx, 25, 1);
                    #    sel_time.tm_sec = nk_propertyi(ctx, "#S:", 0, sel_time.tm_sec, 60, 1, 1);
                    #    sel_time.tm_min = nk_propertyi(ctx, "#M:", 0, sel_time.tm_min, 60, 1, 1);
                    #    sel_time.tm_hour = nk_propertyi(ctx, "#H:", 0, sel_time.tm_hour, 23, 1, 1);
                    #    nk_combo_end(ctx);
                    #}
                    if pynk.lib.nk_combo_begin_label(ctx, sel_time_str, pynk.lib.nk_vec2(200,250)):
                        self.time_selected = True;
                        pynk.lib.nk_layout_row_dynamic(ctx, 25, 1);
                        self.sel_time.second = pynk.lib.nk_propertyi(ctx, "#S:", 0, self.sel_time.second, 60, 1, 1);
                        self.sel_time.minute = pynk.lib.nk_propertyi(ctx, "#M:", 0, self.sel_time.minute, 60, 1, 1);
                        self.sel_time.hour = pynk.lib.nk_propertyi(ctx, "#H:", 0, self.sel_time.hour, 23, 1, 1);
                        pynk.lib.nk_combo_end(ctx);
                    #
                    #/* date combobox */
                    #sprintf(buffer, "%02d-%02d-%02d", sel_date.tm_mday, sel_date.tm_mon+1, sel_date.tm_year+1900);
                    #if (nk_combo_begin_label(ctx, buffer, nk_vec2(350,400)))
                    #{
                    sel_date_str = self.sel_date.strftime("%d-%m-%y")
                    if pynk.lib.nk_combo_begin_label(ctx, sel_date_str, pynk.lib.nk_vec2(350,400)):
                        # int i = 0;
                        # const char *month[] = {"January", "February", "March", "Apil", "May", "June", "July", "August", "September", "Ocotober", "November", "December"};
                        # const char *week_days[] = {"SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"};
                        # const int month_days[] = {31,28,31,30,31,30,31,31,30,31,30,31};
                        # int year = sel_date.tm_year+1900;
                        # int leap_year = (!(year % 4) && ((year % 100))) || !(year % 400);
                        # int days = (sel_date.tm_mon == 1) ?
                        #     month_days[sel_date.tm_mon] + leap_year:
                        #     month_days[sel_date.tm_mon];
                        month = ["January", "February", "March", "Apil", "May", "June", "July", "August", "September", "Ocotober", "November", "December"]
                        week_days = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"]
                        month_days = [31,28,31,30,31,30,31,31,30,31,30,31]
                        year = self.sel_date.year+1900;
                        leap_year = (not (year % 4) and ((year % 100))) or not (year % 400)
                        days = month_days[self.sel_date.month] + leap_year if self.sel_date.month == 1 else month_days[self.sel_date.month];

                        #
                        # /* header with month and year */
                        # date_selected = 1;
                        # nk_layout_row_begin(ctx, NK_DYNAMIC, 20, 3);
                        # nk_layout_row_push(ctx, 0.05f);
                        # if (nk_button_symbol(ctx, NK_SYMBOL_TRIANGLE_LEFT)) {
                        #     if (sel_date.tm_mon == 0) {
                        #         sel_date.tm_mon = 11;
                        #         sel_date.tm_year = MAX(0, sel_date.tm_year-1);
                        #     } else sel_date.tm_mon--;
                        # }
                        # nk_layout_row_push(ctx, 0.9f);
                        # sprintf(buffer, "%s %d", month[sel_date.tm_mon], year);
                        # nk_label(ctx, buffer, NK_TEXT_CENTERED);
                        # nk_layout_row_push(ctx, 0.05f);
                        # if (nk_button_symbol(ctx, NK_SYMBOL_TRIANGLE_RIGHT)) {
                        #     if (sel_date.tm_mon == 11) {
                        #         sel_date.tm_mon = 0;
                        #         sel_date.tm_year++;
                        #     } else sel_date.tm_mon++;
                        # }
                        # nk_layout_row_end(ctx);
                        self.date_selected = True;
                        pynk.lib.nk_layout_row_begin(ctx, pynk.lib.NK_DYNAMIC, 20, 3)
                        pynk.lib.nk_layout_row_push(ctx, 0.05)
                        if pynk.lib.nk_button_symbol(ctx, pynk.lib.NK_SYMBOL_TRIANGLE_LEFT):
                            if self.sel_date.month == 0:
                                self.sel_date.month = 11
                                self.sel_date.year = math.max(0, self.sel_date.year-1)
                            else:
                                self.sel_date.month -= 1
                        pynk.lib.nk_layout_row_push(ctx, 0.9)
                        buf = "%s %s" % (month[self.sel_date.month], year)
                        pynk.lib.nk_label(ctx, buf, pynk.lib.NK_TEXT_CENTERED);
                        pynk.lib.nk_layout_row_push(ctx, 0.05);
                        if pynk.lib.nk_button_symbol(ctx, pynk.lib.NK_SYMBOL_TRIANGLE_RIGHT):
                            if self.sel_date.month == 11:
                                self.sel_date.month = 0
                                self.sel_date.year += 1
                            else:
                                self.sel_date.tm_mon += 1
                        pynk.lib.nk_layout_row_end(ctx);

                        #
                        # /* good old week day formula (double because precision) */
                        # {int year_n = (sel_date.tm_mon < 2) ? year-1: year;
                        # int y = year_n % 100;
                        # int c = year_n / 100;
                        # int y4 = (int)((float)y / 4);
                        # int c4 = (int)((float)c / 4);
                        # int m = (int)(2.6 * (double)(((sel_date.tm_mon + 10) % 12) + 1) - 0.2);
                        # int week_day = (((1 + m + y + y4 + c4 - 2 * c) % 7) + 7) % 7;
                        #
                        # /* weekdays  */
                        # nk_layout_row_dynamic(ctx, 35, 7);
                        # for (i = 0; i < (int)LEN(week_days); ++i)
                        #     nk_label(ctx, week_days[i], NK_TEXT_CENTERED);
                        #
                        # /* days  */
                        # if (week_day > 0) nk_spacing(ctx, week_day);
                        # for (i = 1; i <= days; ++i) {
                        #     sprintf(buffer, "%d", i);
                        #     if (nk_button_label(ctx, buffer)) {
                        #         sel_date.tm_mday = i;
                        #         nk_combo_close(ctx);
                        #     }
                        # }}
                        # nk_combo_end(ctx);
                        year_n = year-1 if self.sel_date.month < 2 else year
                        y = year_n % 100
                        c = year_n / 100
                        y4 = int(y/4.0) # NOTE: is this doing the same thing?
                        c4 = int(c/4.0)
                        m =  int(2.6 * (((self.sel_date.month + 10) % 12) + 1) - 0.2)
                        week_day = (((1 + m + y + y4 + c4 - 2 * c) % 7) + 7) % 7
                        
                        pynk.lib.nk_layout_row_dynamic(ctx, 35, 7)
                        for day in week_days:
                            pynk.lib.nk_label(ctx, day, pynk.lib.NK_TEXT_CENTERED)
                        
                        if week_day > 0:
                            pynk.lib.nk_spacing(ctx, week_day)
                        for i in range(1, days):
                            if pynk.lib.nk_button_label(ctx, str(i)):
                                self.sel_date.day = i
                                pynk.lib.nk_combo_close(ctx)
                        pynk.lib.nk_combo_end(ctx)
                    # }
                    # }
                    #
                    # nk_tree_pop(ctx);
                    pynk.lib.nk_tree_pop(ctx)
                # }
                # if (nk_tree_push(ctx, NK_TREE_NODE, "Input", NK_MINIMIZED))
                # {
                if self.tree_push(ctx, pynk.lib.NK_TREE_NODE, "Input", pynk.lib.NK_MINIMIZED, "10"):
                    # static const float ratio[] = {120, 150};
                    # static char field_buffer[64];
                    # static char text[9][64];
                    # static int text_len[9];
                    # static char box_buffer[512];
                    # static int field_len;
                    # static int box_len;
                    # nk_flags active;
                    self.declare("ratio", [120, 150], "float[]")
                    self.declare("field_buffer", ["a"]*64, "char[]")
                    self.declare_string_buffers("text", 9, 64)
                    self.declare("text_len", [0]*9, "int[]")
                    self.declare("box_buffer", ["a"]*512, "char[]")
                    self.declare("field_len", 0, "int*")
                    self.declare("box_len", 0, "int*")
                    active = 0

    #
                    # nk_layout_row(ctx, NK_STATIC, 25, 2, ratio); #                 nk_label(ctx, "Default:", NK_TEXT_LEFT);
                    #
                    # nk_edit_string(ctx, NK_EDIT_SIMPLE, text[0], &text_len[0], 64, nk_filter_default);
                    # nk_label(ctx, "Int:", NK_TEXT_LEFT);
                    # nk_edit_string(ctx, NK_EDIT_SIMPLE, text[1], &text_len[1], 64, nk_filter_decimal);
                    # nk_label(ctx, "Float:", NK_TEXT_LEFT);
                    # nk_edit_string(ctx, NK_EDIT_SIMPLE, text[2], &text_len[2], 64, nk_filter_float);
                    # nk_label(ctx, "Hex:", NK_TEXT_LEFT);
                    # nk_edit_string(ctx, NK_EDIT_SIMPLE, text[4], &text_len[4], 64, nk_filter_hex);
                    # nk_label(ctx, "Octal:", NK_TEXT_LEFT);
                    # nk_edit_string(ctx, NK_EDIT_SIMPLE, text[5], &text_len[5], 64, nk_filter_oct);
                    # nk_label(ctx, "Binary:", NK_TEXT_LEFT);
                    # nk_edit_string(ctx, NK_EDIT_SIMPLE, text[6], &text_len[6], 64, nk_filter_binary);
    #
                    pynk.lib.nk_layout_row(ctx, pynk.lib.NK_STATIC, 25, 2, self.ratio); #                 nk_label(ctx, "Default:", NK_TEXT_LEFT);

                    pynk.lib.nk_edit_string(ctx, pynk.lib.NK_EDIT_SIMPLE, self.text[0],
                                            self.text_len+0, 64, pynk.ffi.addressof(pynk.lib, "nk_filter_default"));
                    pynk.lib.nk_label(ctx, "Int:", pynk.lib.NK_TEXT_LEFT);
                    pynk.lib.nk_edit_string(ctx, pynk.lib.NK_EDIT_SIMPLE, self.text[1], self.text_len+1,
                                            64, pynk.ffi.addressof(pynk.lib, "nk_filter_decimal"));
                    pynk.lib.nk_label(ctx, "Float:", pynk.lib.NK_TEXT_LEFT);
                    pynk.lib.nk_edit_string(ctx, pynk.lib.NK_EDIT_SIMPLE, self.text[2],
                                            self.text_len+2, 64, pynk.ffi.addressof(pynk.lib, "nk_filter_float"));
                    pynk.lib.nk_label(ctx, "Hex:", pynk.lib.NK_TEXT_LEFT);
                    pynk.lib.nk_edit_string(ctx, pynk.lib.NK_EDIT_SIMPLE, self.text[4],
                                            self.text_len+4, 64, pynk.ffi.addressof(pynk.lib, "nk_filter_hex"));
                    pynk.lib.nk_label(ctx, "Octal:", pynk.lib.NK_TEXT_LEFT);
                    pynk.lib.nk_edit_string(ctx, pynk.lib.NK_EDIT_SIMPLE, self.text[5],
                                            self.text_len+5, 64, pynk.ffi.addressof(pynk.lib, "nk_filter_oct"));
                    pynk.lib.nk_label(ctx, "Binary:", pynk.lib.NK_TEXT_LEFT);
                    pynk.lib.nk_edit_string(ctx, pynk.lib.NK_EDIT_SIMPLE, self.text[6],
                                           self.text_len+6, 64, pynk.ffi.addressof(pynk.lib, "nk_filter_binary"));
                    #
                    # nk_label(ctx, "Password:", NK_TEXT_LEFT);
                    # {
                    #     int i = 0;
                    #     int old_len = text_len[8];
                    #     char buffer[64];
                    #     for (i = 0; i < text_len[8]; ++i) buffer[i] = '*';
                    #     nk_edit_string(ctx, NK_EDIT_FIELD, buffer, &text_len[8], 64, nk_filter_default);
                    #     if (old_len < text_len[8])
                    #         memcpy(&text[8][old_len], &buffer[old_len], (nk_size)(text_len[8] - old_len));
                    # }
                    pynk.lib.nk_label(ctx, "Password:", pynk.lib.NK_TEXT_LEFT);
                    old_len = self.text_len[8];
                    buf = pynk.ffi.new("char[64]")
                    for i in range(0, self.text_len[8]):
                        buf[i] = "*"
                    pynk.lib.nk_edit_string(ctx, pynk.lib.NK_EDIT_FIELD, buf, self.text_len+8,
                                            64, pynk.ffi.addressof(pynk.lib, "nk_filter_default"));
                    if old_len < self.text_len[8]:
                        self.memcpy(self.text+8, old_len, buf, old_len, self.text_len[8] - old_len);
                    #
                    #  nk_label(ctx, "Field:", NK_TEXT_LEFT);
                    #  nk_edit_string(ctx, NK_EDIT_FIELD, field_buffer, &field_len, 64, nk_filter_default);
                    #
                    #  nk_label(ctx, "Box:", NK_TEXT_LEFT);
                    #  nk_layout_row_static(ctx, 180, 278, 1);
                    #  nk_edit_string(ctx, NK_EDIT_BOX, box_buffer, &box_len, 512, nk_filter_default);
                    #
                    #  nk_layout_row(ctx, NK_STATIC, 25, 2, ratio);
                    #  active = nk_edit_string(ctx, NK_EDIT_FIELD|NK_EDIT_SIG_ENTER, text[7], &text_len[7], 64,  nk_filter_ascii);

                    pynk.lib.nk_label(ctx, "Field:", pynk.lib.NK_TEXT_LEFT);
                    pynk.lib.nk_edit_string(ctx, pynk.lib.NK_EDIT_FIELD, self.field_buffer,
                                            self.field_len, 64, pynk.ffi.addressof(pynk.lib, "nk_filter_default"));

                    pynk.lib.nk_label(ctx, "Box:", pynk.lib.NK_TEXT_LEFT);
                    pynk.lib.nk_layout_row_static(ctx, 180, 278, 1);
                    pynk.lib.nk_edit_string(ctx, pynk.lib.NK_EDIT_BOX, self.box_buffer, self.box_len,
                                            512, pynk.ffi.addressof(pynk.lib, "nk_filter_default"));

                    pynk.lib.nk_layout_row(ctx, pynk.lib.NK_STATIC, 25, 2, self.ratio);
                    active = pynk.lib.nk_edit_string(ctx, pynk.lib.NK_EDIT_FIELD|pynk.lib.NK_EDIT_SIG_ENTER,
                                            self.text[7], self.text_len+7, 64, pynk.ffi.addressof(pynk.lib, "nk_filter_ascii"));
                    # if (nk_button_label(ctx, "Submit") ||
                    #     (active & NK_EDIT_COMMITED))
                    # {
                    #     text[7][text_len[7]] = '\n';
                    #     text_len[7]++;
                    #     memcpy(&box_buffer[box_len], &text[7], (nk_size)text_len[7]);
                    #     box_len += text_len[7];
                    #     text_len[7] = 0;
                    # }
                    # nk_tree_pop(ctx);
                    if pynk.lib.nk_button_label(ctx, "Submit") or (active & pynk.lib.NK_EDIT_COMMITED):
                        self.text[7][self.text_len[7]] = '\n';
                        self.text_len[7] += 1
                        #TODO: memcpy(&box_buffer[box_len], &text[7], (nk_size)text_len[7]);
                        self.box_len += self.text_len[7];
                        self.text_len[7] = 0;
                    pynk.lib.nk_tree_pop(ctx);

                pynk.lib.nk_tree_pop(ctx); #widgets

            # }
            #
            # if (nk_tree_push(ctx, NK_TREE_TAB, "Chart", NK_MINIMIZED))
            # {
            if self.tree_push(ctx, pynk.lib.NK_TREE_TAB, "Chart", pynk.lib.NK_MINIMIZED, "11"):
                # /* Chart Widgets
                #  * This library has two different rather simple charts. The line and the
                #  * column chart. Both provide a simple way of visualizing values and
                #  * have a retained mode and immediate mode API version. For the retain
                #  * mode version `nk_plot` and `nk_plot_function` you either provide
                #  * an array or a callback to call to handle drawing the graph.
                #  * For the immediate mode version you start by calling `nk_chart_begin`
                #  * and need to provide min and max values for scaling on the Y-axis.
                #  * and then call `nk_chart_push` to push values into the chart.
                #  * Finally `nk_chart_end` needs to be called to end the process. */
                # float id = 0;
                # static int col_index = -1;
                # static int line_index = -1;
                # float step = (2*3.141592654f) / 32;
                #
                # int i;
                # int index = -1;
                # struct nk_rect bounds;
                id = 0
                col_index = -1
                line_index = -1
                step = (2*3.141592654) / 32;
                step = (2*3.141592654) / 32;
                index = -1;

                # nk_layout_row_dynamic(ctx, 100, 1);
                # if (nk_chart_begin(ctx, NK_CHART_LINES, 32, -1.0f, 1.0f)) {
                #     for (i = 0; i < 32; ++i) {
                #         nk_flags res = nk_chart_push(ctx, (float)cos(id));
                #         if (res & NK_CHART_HOVERING)
                #             index = (int)i;
                #         if (res & NK_CHART_CLICKED)
                #             line_index = (int)i;
                #         id += step;
                #     }
                #     nk_chart_end(ctx);
                # }
                pynk.lib.nk_layout_row_dynamic(ctx, 100, 1);
                if pynk.lib.nk_chart_begin(ctx, pynk.lib.NK_CHART_LINES, 32, -1.0, 1.0):
                    for i in xrange(32):
                        res = pynk.lib.nk_chart_push(ctx, math.cos(id))
                        if res & pynk.lib.NK_CHART_HOVERING:
                            index = i
                        if res & pynk.lib.NK_CHART_CLICKED:
                            line_index = i
                        id += step;
                pynk.lib.nk_chart_end(ctx);
                #
                # if (index != -1)
                #     nk_tooltipf(ctx, "Value: %.2f", (float)cos((float)index*step));
                # if (line_index != -1) {
                #     nk_layout_row_dynamic(ctx, 20, 1);
                #     nk_labelf(ctx, NK_TEXT_LEFT, "Selected value: %.2f", (float)cos((float)index*step));
                # }

                if index != -1:
                    pynk.lib.nk_tooltipf(ctx, "Value: %.2f", pynk.ffi.cast("float", math.cos(index*step)))
                if line_index != -1:
                    pynk.lib.nk_layout_row_dynamic(ctx, 20, 1);
                    pynk.lib.nk_labelf(ctx, pynk.lib.NK_TEXT_LEFT, "Selected value: %.2f", math.cos(index*step))

                # /* column chart */
                # nk_layout_row_dynamic(ctx, 100, 1);
                # bounds = nk_widget_bounds(ctx);
                # if (nk_chart_begin(ctx, NK_CHART_COLUMN, 32, 0.0f, 1.0f)) {
                #     for (i = 0; i < 32; ++i) {
                #         nk_flags res = nk_chart_push(ctx, (float)fabs(sin(id)));
                #         if (res & NK_CHART_HOVERING)
                #             index = (int)i;
                #         if (res & NK_CHART_CLICKED)
                #             col_index = (int)i;
                #         id += step;
                #     }
                #     nk_chart_end(ctx);
                # }
                # if (index != -1)
                #     nk_tooltipf(ctx, "Value: %.2f", (float)fabs(sin(step * (float)index)));
                # if (col_index != -1) {
                #     nk_layout_row_dynamic(ctx, 20, 1);
                #     nk_labelf(ctx, NK_TEXT_LEFT, "Selected value: %.2f", (float)fabs(sin(step * (float)col_index)));
                # }
                pynk.lib.nk_layout_row_dynamic(ctx, 100, 1);
                bounds = pynk.lib.nk_widget_bounds(ctx);
                if pynk.lib.nk_chart_begin(ctx, pynk.lib.NK_CHART_COLUMN, 32, 0.0, 1.0):
                    for i in xrange(32):
                        res = pynk.lib.nk_chart_push(ctx, math.fabs(math.sin(id)))
                        if res & pynk.lib.NK_CHART_HOVERING:
                            index = i
                        if res & pynk.lib.NK_CHART_CLICKED:
                            col_index = i
                        id += step;
                    pynk.lib.nk_chart_end(ctx);
                if index != -1:
                    pynk.lib.nk_tooltipf(ctx, "Value: %.2f", pynk.ffi.cast("float", math.fabs(math.sin(step * index))))
                if col_index != -1:
                    pynk.lib.nk_layout_row_dynamic(ctx, 20, 1)
                    pynk.lib.nk_labelf(ctx, pynk.lib.NK_TEXT_LEFT, "Selected value: %.2f", pynk.ffi.cast("float", math.fabs(math.sin(step * col_index))))
                #
                # /* mixed chart */
                # nk_layout_row_dynamic(ctx, 100, 1);
                # bounds = nk_widget_bounds(ctx);
                # if (nk_chart_begin(ctx, NK_CHART_COLUMN, 32, 0.0f, 1.0f)) {
                #     nk_chart_add_slot(ctx, NK_CHART_LINES, 32, -1.0f, 1.0f);
                #     nk_chart_add_slot(ctx, NK_CHART_LINES, 32, -1.0f, 1.0f);
                #     for (id = 0, i = 0; i < 32; ++i) {
                #         nk_chart_push_slot(ctx, (float)fabs(sin(id)), 0);
                #         nk_chart_push_slot(ctx, (float)cos(id), 1);
                #         nk_chart_push_slot(ctx, (float)sin(id), 2);
                #         id += step;
                #     }
                # }
                # nk_chart_end(ctx);
                pynk.lib.nk_layout_row_dynamic(ctx, 100, 1)
                bounds = pynk.lib.nk_widget_bounds(ctx)
                if pynk.lib.nk_chart_begin(ctx, pynk.lib.NK_CHART_COLUMN, 32, 0.0, 1.0):
                    pynk.lib.nk_chart_add_slot(ctx, pynk.lib.NK_CHART_LINES, 32, -1.0, 1.0)
                    pynk.lib.nk_chart_add_slot(ctx, pynk.lib.NK_CHART_LINES, 32, -1.0, 1.0)
                    id = 0 # TODO: check for previous weird fors like this.
                    for i in xrange(32):
                        pynk.lib.nk_chart_push_slot(ctx, math.fabs(math.sin(id)), 0)
                        pynk.lib.nk_chart_push_slot(ctx, math.cos(id), 1)
                        pynk.lib.nk_chart_push_slot(ctx, math.sin(id), 2)
                        id += step;
                pynk.lib.nk_chart_end(ctx);
                #
                # /* mixed colored chart */
                # nk_layout_row_dynamic(ctx, 100, 1);
                # bounds = nk_widget_bounds(ctx);
                # if (nk_chart_begin_colored(ctx, NK_CHART_LINES, nk_rgb(255,0,0), nk_rgb(150,0,0), 32, 0.0f, 1.0f)) {
                #     nk_chart_add_slot_colored(ctx, NK_CHART_LINES, nk_rgb(0,0,255), nk_rgb(0,0,150),32, -1.0f, 1.0f);
                #     nk_chart_add_slot_colored(ctx, NK_CHART_LINES, nk_rgb(0,255,0), nk_rgb(0,150,0), 32, -1.0f, 1.0f);
                #     for (id = 0, i = 0; i < 32; ++i) {
                #         nk_chart_push_slot(ctx, (float)fabs(sin(id)), 0);
                #         nk_chart_push_slot(ctx, (float)cos(id), 1);
                #         nk_chart_push_slot(ctx, (float)sin(id), 2);
                #         id += step;
                #     }
                # }
                # nk_chart_end(ctx);
                # nk_tree_pop(ctx);
                pynk.lib.nk_layout_row_dynamic(ctx, 100, 1)
                bounds = pynk.lib.nk_widget_bounds(ctx)
                if pynk.lib.nk_chart_begin_colored(ctx, pynk.lib.NK_CHART_LINES, pynk.lib.nk_rgb(255,0,0), pynk.lib.nk_rgb(150,0,0), 32, 0.0, 1.0):
                    pynk.lib.nk_chart_add_slot_colored(ctx, pynk.lib.NK_CHART_LINES, pynk.lib.nk_rgb(0,0,255), pynk.lib.nk_rgb(0,0,150),32, -1.0, 1.0)
                    pynk.lib.nk_chart_add_slot_colored(ctx, pynk.lib.NK_CHART_LINES, pynk.lib.nk_rgb(0,255,0), pynk.lib.nk_rgb(0,150,0), 32, -1.0, 1.0)
                    id = 0
                    for i in xrange(32):
                        pynk.lib.nk_chart_push_slot(ctx, math.fabs(math.sin(id)), 0)
                        pynk.lib.nk_chart_push_slot(ctx, math.cos(id), 1)
                        pynk.lib.nk_chart_push_slot(ctx, math.sin(id), 2)
                        id += step;
                pynk.lib.nk_chart_end(ctx);
                pynk.lib.nk_tree_pop(ctx);

            # }
            #
            # if (nk_tree_push(ctx, NK_TREE_TAB, "Popup", NK_MINIMIZED))
            # {
            if self.tree_push(ctx, pynk.lib.NK_TREE_TAB, "Popup", pynk.lib.NK_MINIMIZED, "12"):
                # static struct nk_color color = {255,0,0, 255};
                # static int select[4];
                # static int popup_active;
                # const struct nk_input *in = &ctx->input;
                # struct nk_rect bounds;
                self.declare("color", [255,0,0, 255], "struct nk_color*")
                self.declare("select", [0]*4, "int[]")
                self.declare("popup_active", False)
                bounds = pynk.ffi.new("struct nk_rect*")

                # /* menu contextual */
                # nk_layout_row_static(ctx, 30, 150, 1);
                # bounds = nk_widget_bounds(ctx);
                # nk_label(ctx, "Right click me for menu", NK_TEXT_LEFT);
                #
                # if (nk_contextual_begin(ctx, 0, nk_vec2(100, 300), bounds)) {
                #     static size_t prog = 40;
                #     static int slider = 10;
                #
                #     nk_layout_row_dynamic(ctx, 25, 1);
                #     nk_checkbox_label(ctx, "Menu", &show_menu);
                #     nk_progress(ctx, &prog, 100, NK_MODIFIABLE);
                #     nk_slider_int(ctx, 0, &slider, 16, 1);
                #     if (nk_contextual_item_label(ctx, "About", NK_TEXT_CENTERED))
                #         show_app_about = nk_true;
                #     nk_selectable_label(ctx, select[0]?"Unselect":"Select", NK_TEXT_LEFT, &select[0]);
                #     nk_selectable_label(ctx, select[1]?"Unselect":"Select", NK_TEXT_LEFT, &select[1]);
                #     nk_selectable_label(ctx, select[2]?"Unselect":"Select", NK_TEXT_LEFT, &select[2]);
                #     nk_selectable_label(ctx, select[3]?"Unselect":"Select", NK_TEXT_LEFT, &select[3]);
                #     nk_contextual_end(ctx);
                # }
                pynk.lib.nk_layout_row_static(ctx, 30, 150, 1);
                bounds = pynk.lib.nk_widget_bounds(ctx);
                pynk.lib.nk_label(ctx, "Right click me for menu", pynk.lib.NK_TEXT_LEFT);

                if pynk.lib.nk_contextual_begin(ctx, 0, pynk.lib.nk_vec2(100, 300), bounds):
                    self.declare("prog", 40, "unsigned int*")
                    self.declare("slider", 10, "int*")

                    pynk.lib.nk_layout_row_dynamic(ctx, 25, 1)
                    pynk.lib.nk_checkbox_label(ctx, "Menu", self.show_menu)
                    pynk.lib.nk_progress(ctx, self.prog, 100, pynk.lib.NK_MODIFIABLE)
                    pynk.lib.nk_slider_int(ctx, 0, self.slider, 16, 1)
                    if pynk.lib.nk_contextual_item_label(ctx, "About", pynk.lib.NK_TEXT_CENTERED):
                        self.show_app_about[0] = 1
                    pynk.lib.nk_selectable_label(ctx, "Unselect" if self.select[0] else "Select", pynk.lib.NK_TEXT_LEFT, self.select+0)
                    pynk.lib.nk_selectable_label(ctx, "Unselect" if self.select[1] else "Select", pynk.lib.NK_TEXT_LEFT, self.select+1);
                    pynk.lib.nk_selectable_label(ctx, "Unselect" if self.select[2] else "Select", pynk.lib.NK_TEXT_LEFT, self.select+2);
                    pynk.lib.nk_selectable_label(ctx, "Unselect" if self.select[3] else "Select", pynk.lib.NK_TEXT_LEFT, self.select+3);
                    pynk.lib.nk_contextual_end(ctx);

                # /* color contextual */
                # nk_layout_row_begin(ctx, NK_STATIC, 30, 2);
                # nk_layout_row_push(ctx, 100);
                # nk_label(ctx, "Right Click here:", NK_TEXT_LEFT);
                # nk_layout_row_push(ctx, 50);
                # bounds = nk_widget_bounds(ctx);
                # nk_button_color(ctx, color);
                # nk_layout_row_end(ctx);
                #
                # if (nk_contextual_begin(ctx, 0, nk_vec2(350, 60), bounds)) {
                #     nk_layout_row_dynamic(ctx, 30, 4);
                #     color.r = (nk_byte)nk_propertyi(ctx, "#r", 0, color.r, 255, 1, 1);
                #     color.g = (nk_byte)nk_propertyi(ctx, "#g", 0, color.g, 255, 1, 1);
                #     color.b = (nk_byte)nk_propertyi(ctx, "#b", 0, color.b, 255, 1, 1);
                #     color.a = (nk_byte)nk_propertyi(ctx, "#a", 0, color.a, 255, 1, 1);
                #     nk_contextual_end(ctx);
                # }
                pynk.lib.nk_layout_row_begin(ctx, pynk.lib.NK_STATIC, 30, 2);
                pynk.lib.nk_layout_row_push(ctx, 100);
                pynk.lib.nk_label(ctx, "Right Click here:", pynk.lib.NK_TEXT_LEFT);
                pynk.lib.nk_layout_row_push(ctx, 50);
                bounds = pynk.lib.nk_widget_bounds(ctx);
                pynk.lib.nk_button_color(ctx, self.color[0]);
                pynk.lib.nk_layout_row_end(ctx);

                if pynk.lib.nk_contextual_begin(ctx, 0, pynk.lib.nk_vec2(350, 60), bounds):
                    pynk.lib.nk_layout_row_dynamic(ctx, 30, 4);
                    self.color.r = pynk.lib.nk_propertyi(ctx, "#r", 0, self.color.r, 255, 1, 1)
                    self.color.g = pynk.lib.nk_propertyi(ctx, "#g", 0, self.color.g, 255, 1, 1)
                    self.color.b = pynk.lib.nk_propertyi(ctx, "#b", 0, self.color.b, 255, 1, 1)
                    self.color.a = pynk.lib.nk_propertyi(ctx, "#a", 0, self.color.a, 255, 1, 1)
                    pynk.lib.nk_contextual_end(ctx)
                #
                # /* popup */
                # nk_layout_row_begin(ctx, NK_STATIC, 30, 2);
                # nk_layout_row_push(ctx, 100);
                # nk_label(ctx, "Popup:", NK_TEXT_LEFT);
                # nk_layout_row_push(ctx, 50);
                # if (nk_button_label(ctx, "Popup"))
                #     popup_active = 1;
                # nk_layout_row_end(ctx);
                #
                # if (popup_active)
                # {
                #     static struct nk_rect s = {20, 100, 220, 90};
                #     if (nk_popup_begin(ctx, NK_POPUP_STATIC, "Error", 0, s))
                #     {
                #         nk_layout_row_dynamic(ctx, 25, 1);
                #         nk_label(ctx, "A terrible error as occured", NK_TEXT_LEFT);
                #         nk_layout_row_dynamic(ctx, 25, 2);
                #         if (nk_button_label(ctx, "OK")) {
                #             popup_active = 0;
                #             nk_popup_close(ctx);
                #         }
                #         if (nk_button_label(ctx, "Cancel")) {
                #             popup_active = 0;
                #             nk_popup_close(ctx);
                #         }
                #         nk_popup_end(ctx);
                #     } else popup_active = nk_false;
                # }
                pynk.lib.nk_layout_row_begin(ctx, pynk.lib.NK_STATIC, 30, 2);
                pynk.lib.nk_layout_row_push(ctx, 100);
                pynk.lib.nk_label(ctx, "Popup:", pynk.lib.NK_TEXT_LEFT);
                pynk.lib.nk_layout_row_push(ctx, 50);
                if pynk.lib.nk_button_label(ctx, "Popup"):
                    self.popup_active = 1;
                pynk.lib.nk_layout_row_end(ctx);
                if self.popup_active:
                    if pynk.lib.nk_popup_begin(ctx, pynk.lib.NK_POPUP_STATIC, "Error", 0, pynk.lib.nk_rect(20, 100, 220, 90)):
                        pynk.lib.nk_layout_row_dynamic(ctx, 25, 1);
                        pynk.lib.nk_label(ctx, "A terrible error as occured", pynk.lib.NK_TEXT_LEFT);
                        pynk.lib.nk_layout_row_dynamic(ctx, 25, 2);
                        if pynk.lib.nk_button_label(ctx, "OK"):
                            self.popup_active = 0;
                            pynk.lib.nk_popup_close(ctx);
                        if pynk.lib.nk_button_label(ctx, "Cancel"):
                            self.popup_active = 0;
                            pynk.lib.nk_popup_close(ctx);
                        pynk.lib.nk_popup_end(ctx);
                    else: self.popup_active = 0
                #
                # /* tooltip */
                # nk_layout_row_static(ctx, 30, 150, 1);
                # bounds = nk_widget_bounds(ctx);
                # nk_label(ctx, "Hover me for tooltip", NK_TEXT_LEFT);
                # if (nk_input_is_mouse_hovering_rect(in, bounds))
                #     nk_tooltip(ctx, "This is a tooltip");
                #
                # nk_tree_pop(ctx);
                pynk.lib.nk_layout_row_static(ctx, 30, 150, 1);
                bounds = pynk.lib.nk_widget_bounds(ctx);
                pynk.lib.nk_label(ctx, "Hover me for tooltip", pynk.lib.NK_TEXT_LEFT);
                inp = pynk.ffi.addressof(ctx, "input")
                if pynk.lib.nk_input_is_mouse_hovering_rect(inp, bounds):
                    pynk.lib.nk_tooltip(ctx, "This is a tooltip");

                pynk.lib.nk_tree_pop(ctx);
            # }
            #
            # if (nk_tree_push(ctx, NK_TREE_TAB, "Layout", NK_MINIMIZED))
            # {
            if self.tree_push(ctx, pynk.lib.NK_TREE_TAB, "Layout", pynk.lib.NK_MINIMIZED, "13"):
                # if (nk_tree_push(ctx, NK_TREE_NODE, "Widget", NK_MINIMIZED))
                # {
                if self.tree_push(ctx, pynk.lib.NK_TREE_NODE, "Widget", pynk.lib.NK_MINIMIZED, "14"):
                    # float ratio_two[] = {0.2f, 0.6f, 0.2f};
                    # float width_two[] = {100, 200, 50};
                    ratio_two = pynk.ffi.new("float[]", [0.2, 0.6, 0.2])
                    width_two = pynk.ffi.new("float[]", [100, 200, 50])
                    #
                    # nk_layout_row_dynamic(ctx, 30, 1);
                    # nk_label(ctx, "Dynamic fixed column layout with generated position and size:", NK_TEXT_LEFT);
                    # nk_layout_row_dynamic(ctx, 30, 3);
                    # nk_button_label(ctx, "button");
                    # nk_button_label(ctx, "button");
                    # nk_button_label(ctx, "button");
                    pynk.lib.nk_layout_row_dynamic(ctx, 30, 1);
                    pynk.lib.nk_label(ctx, "Dynamic fixed column layout with generated position and size:", pynk.lib.NK_TEXT_LEFT);
                    pynk.lib.nk_layout_row_dynamic(ctx, 30, 3);
                    pynk.lib.nk_button_label(ctx, "button");
                    pynk.lib.nk_button_label(ctx, "button");
                    pynk.lib.nk_button_label(ctx, "button");
                    #
                    # nk_layout_row_dynamic(ctx, 30, 1);
                    # nk_label(ctx, "static fixed column layout with generated position and size:", NK_TEXT_LEFT);
                    # nk_layout_row_static(ctx, 30, 100, 3);
                    # nk_button_label(ctx, "button");
                    # nk_button_label(ctx, "button");
                    # nk_button_label(ctx, "button");
                    pynk.lib.nk_layout_row_dynamic(ctx, 30, 1);
                    pynk.lib.nk_label(ctx, "static fixed column layout with generated position and size:", pynk.lib.NK_TEXT_LEFT);
                    pynk.lib.nk_layout_row_static(ctx, 30, 100, 3);
                    pynk.lib.nk_button_label(ctx, "button");
                    pynk.lib.nk_button_label(ctx, "button");
                    pynk.lib.nk_button_label(ctx, "button");
                    #
                    # nk_layout_row_dynamic(ctx, 30, 1);
                    # nk_label(ctx, "Dynamic array-based custom column layout with generated position and custom size:",NK_TEXT_LEFT);
                    # nk_layout_row(ctx, NK_DYNAMIC, 30, 3, ratio_two);
                    # nk_button_label(ctx, "button");
                    # nk_button_label(ctx, "button");
                    # nk_button_label(ctx, "button");
                    pynk.lib.nk_layout_row_dynamic(ctx, 30, 1);
                    pynk.lib.nk_label(ctx, "Dynamic array-based custom column layout with generated position and custom size:",pynk.lib.NK_TEXT_LEFT);
                    pynk.lib.nk_layout_row(ctx, pynk.lib.NK_DYNAMIC, 30, 3, ratio_two);
                    pynk.lib.nk_button_label(ctx, "button");
                    pynk.lib.nk_button_label(ctx, "button");
                    pynk.lib.nk_button_label(ctx, "button");
                    #
                    # nk_layout_row_dynamic(ctx, 30, 1);
                    # nk_label(ctx, "Static array-based custom column layout with generated position and custom size:",NK_TEXT_LEFT );
                    # nk_layout_row(ctx, NK_STATIC, 30, 3, width_two);
                    # nk_button_label(ctx, "button");
                    # nk_button_label(ctx, "button");
                    # nk_button_label(ctx, "button");
                    pynk.lib.nk_layout_row_dynamic(ctx, 30, 1);
                    pynk.lib.nk_label(ctx, "Static array-based custom column layout with generated position and custom size:",pynk.lib.NK_TEXT_LEFT );
                    pynk.lib.nk_layout_row(ctx, pynk.lib.NK_STATIC, 30, 3, width_two);
                    pynk.lib.nk_button_label(ctx, "button");
                    pynk.lib.nk_button_label(ctx, "button");
                    pynk.lib.nk_button_label(ctx, "button");
                    #
                    # nk_layout_row_dynamic(ctx, 30, 1);
                    # nk_label(ctx, "Dynamic immediate mode custom column layout with generated position and custom size:",NK_TEXT_LEFT);
                    # nk_layout_row_begin(ctx, NK_DYNAMIC, 30, 3);
                    # nk_layout_row_push(ctx, 0.2f);
                    # nk_button_label(ctx, "button");
                    # nk_layout_row_push(ctx, 0.6f);
                    # nk_button_label(ctx, "button");
                    # nk_layout_row_push(ctx, 0.2f);
                    # nk_button_label(ctx, "button");
                    # nk_layout_row_end(ctx);
                    pynk.lib.nk_layout_row_dynamic(ctx, 30, 1);
                    pynk.lib.nk_label(ctx, "Dynamic immediate mode custom column layout with generated position and custom size:",pynk.lib.NK_TEXT_LEFT);
                    pynk.lib.nk_layout_row_begin(ctx, pynk.lib.NK_DYNAMIC, 30, 3);
                    pynk.lib.nk_layout_row_push(ctx, 0.2);
                    pynk.lib.nk_button_label(ctx, "button");
                    pynk.lib.nk_layout_row_push(ctx, 0.6);
                    pynk.lib.nk_button_label(ctx, "button");
                    pynk.lib.nk_layout_row_push(ctx, 0.2);
                    pynk.lib.nk_button_label(ctx, "button");
                    pynk.lib.nk_layout_row_end(ctx);
                    #
                    # nk_layout_row_dynamic(ctx, 30, 1);
                    # nk_label(ctx, "Static immediate mode custom column layout with generated position and custom size:", NK_TEXT_LEFT);
                    # nk_layout_row_begin(ctx, NK_STATIC, 30, 3);
                    # nk_layout_row_push(ctx, 100);
                    # nk_button_label(ctx, "button");
                    # nk_layout_row_push(ctx, 200);
                    # nk_button_label(ctx, "button");
                    # nk_layout_row_push(ctx, 50);
                    # nk_button_label(ctx, "button");
                    # nk_layout_row_end(ctx);
                    #
                    pynk.lib.nk_layout_row_dynamic(ctx, 30, 1);
                    pynk.lib.nk_label(ctx, "Static immediate mode custom column layout with generated position and custom size:", pynk.lib.NK_TEXT_LEFT);
                    pynk.lib.nk_layout_row_begin(ctx, pynk.lib.NK_STATIC, 30, 3);
                    pynk.lib.nk_layout_row_push(ctx, 100);
                    pynk.lib.nk_button_label(ctx, "button");
                    pynk.lib.nk_layout_row_push(ctx, 200);
                    pynk.lib.nk_button_label(ctx, "button");
                    pynk.lib.nk_layout_row_push(ctx, 50);
                    pynk.lib.nk_button_label(ctx, "button");
                    pynk.lib.nk_layout_row_end(ctx);
                    #
                    # nk_layout_row_dynamic(ctx, 30, 1);
                    # nk_label(ctx, "Static free space with custom position and custom size:", NK_TEXT_LEFT);
                    # nk_layout_space_begin(ctx, NK_STATIC, 60, 4);
                    # nk_layout_space_push(ctx, nk_rect(100, 0, 100, 30));
                    # nk_button_label(ctx, "button");
                    # nk_layout_space_push(ctx, nk_rect(0, 15, 100, 30));
                    # nk_button_label(ctx, "button");
                    # nk_layout_space_push(ctx, nk_rect(200, 15, 100, 30));
                    # nk_button_label(ctx, "button");
                    # nk_layout_space_push(ctx, nk_rect(100, 30, 100, 30));
                    # nk_button_label(ctx, "button");
                    # nk_layout_space_end(ctx);
                    pynk.lib.nk_layout_row_dynamic(ctx, 30, 1);
                    pynk.lib.nk_label(ctx, "Static free space with custom position and custom size:", pynk.lib.NK_TEXT_LEFT);
                    pynk.lib.nk_layout_space_begin(ctx, pynk.lib.NK_STATIC, 60, 4);
                    pynk.lib.nk_layout_space_push(ctx, pynk.lib.nk_rect(100, 0, 100, 30));
                    pynk.lib.nk_button_label(ctx, "button");
                    pynk.lib.nk_layout_space_push(ctx, pynk.lib.nk_rect(0, 15, 100, 30));
                    pynk.lib.nk_button_label(ctx, "button");
                    pynk.lib.nk_layout_space_push(ctx, pynk.lib.nk_rect(200, 15, 100, 30));
                    pynk.lib.nk_button_label(ctx, "button");
                    pynk.lib.nk_layout_space_push(ctx, pynk.lib.nk_rect(100, 30, 100, 30));
                    pynk.lib.nk_button_label(ctx, "button");
                    pynk.lib.nk_layout_space_end(ctx);
                    #
                    # nk_layout_row_dynamic(ctx, 30, 1);
                    # nk_label(ctx, "Row template:", NK_TEXT_LEFT);
                    # nk_layout_row_template_begin(ctx, 30);
                    # nk_layout_row_template_push_dynamic(ctx);
                    # nk_layout_row_template_push_variable(ctx, 80);
                    # nk_layout_row_template_push_static(ctx, 80);
                    # nk_layout_row_template_end(ctx);
                    # nk_button_label(ctx, "button");
                    # nk_button_label(ctx, "button");
                    # nk_button_label(ctx, "button");
                    pynk.lib.nk_layout_row_dynamic(ctx, 30, 1);
                    pynk.lib.nk_label(ctx, "Row template:", pynk.lib.NK_TEXT_LEFT);
                    pynk.lib.nk_layout_row_template_begin(ctx, 30);
                    pynk.lib.nk_layout_row_template_push_dynamic(ctx);
                    pynk.lib.nk_layout_row_template_push_variable(ctx, 80);
                    pynk.lib.nk_layout_row_template_push_static(ctx, 80);
                    pynk.lib.nk_layout_row_template_end(ctx);
                    pynk.lib.nk_button_label(ctx, "button");
                    pynk.lib.nk_button_label(ctx, "button");
                    pynk.lib.nk_button_label(ctx, "button");
                    #
                    # nk_tree_pop(ctx);
                    pynk.lib.nk_tree_pop(ctx);
                # }
                #
                # if (nk_tree_push(ctx, NK_TREE_NODE, "Group", NK_MINIMIZED))
                # {
                if self.tree_push(ctx, pynk.lib.NK_TREE_NODE, "Group", pynk.lib.NK_MINIMIZED, "15"):
                    # static int group_titlebar = nk_false;
                    # static int group_border = nk_true;
                    # static int group_no_scrollbar = nk_false;
                    # static int group_width = 320;
                    # static int group_height = 200;
                    self.declare("group_titlebar", 0, "int*")
                    self.declare("group_border", 1, "int*")
                    self.declare("group_no_scrollbar", 0, "int*")
                    self.declare("group_width", 320, "int*")
                    self.declare("group_height", 200, "int*")
                    #
                    # nk_flags group_flags = 0;
                    # if (group_border) group_flags |= NK_WINDOW_BORDER;
                    # if (group_no_scrollbar) group_flags |= NK_WINDOW_NO_SCROLLBAR;
                    # if (group_titlebar) group_flags |= NK_WINDOW_TITLE;
                    group_flags = 0;
                    if self.group_border[0]: group_flags |= pynk.lib.NK_WINDOW_BORDER;
                    if self.group_no_scrollbar[0]: group_flags |= pynk.lib.NK_WINDOW_NO_SCROLLBAR;
                    if self.group_titlebar[0]: group_flags |= pynk.lib.NK_WINDOW_TITLE;
                    #
                    # nk_layout_row_dynamic(ctx, 30, 3);
                    # nk_checkbox_label(ctx, "Titlebar", &group_titlebar);
                    # nk_checkbox_label(ctx, "Border", &group_border);
                    # nk_checkbox_label(ctx, "No Scrollbar", &group_no_scrollbar);
                    pynk.lib.nk_layout_row_dynamic(ctx, 30, 3);
                    pynk.lib.nk_checkbox_label(ctx, "Titlebar", self.group_titlebar);
                    pynk.lib.nk_checkbox_label(ctx, "Border", self.group_border);
                    pynk.lib.nk_checkbox_label(ctx, "No Scrollbar", self.group_no_scrollbar);
                    #
                    # nk_layout_row_begin(ctx, NK_STATIC, 22, 3);
                    # nk_layout_row_push(ctx, 50);
                    # nk_label(ctx, "size:", NK_TEXT_LEFT);
                    # nk_layout_row_push(ctx, 130);
                    # nk_property_int(ctx, "#Width:", 100, &group_width, 500, 10, 1);
                    # nk_layout_row_push(ctx, 130);
                    # nk_property_int(ctx, "#Height:", 100, &group_height, 500, 10, 1);
                    # nk_layout_row_end(ctx);
                    pynk.lib.nk_layout_row_begin(ctx, pynk.lib.NK_STATIC, 22, 3);
                    pynk.lib.nk_layout_row_push(ctx, 50);
                    pynk.lib.nk_label(ctx, "size:", pynk.lib.NK_TEXT_LEFT);
                    pynk.lib.nk_layout_row_push(ctx, 130);
                    pynk.lib.nk_property_int(ctx, "#Width:", 100, self.group_width, 500, 10, 1);
                    pynk.lib.nk_layout_row_push(ctx, 130);
                    pynk.lib.nk_property_int(ctx, "#Height:", 100, self.group_height, 500, 10, 1);
                    pynk.lib.nk_layout_row_end(ctx);
                    #
                    # nk_layout_row_static(ctx, (float)group_height, group_width, 2);
                    # if (nk_group_begin(ctx, "Group", group_flags)) {
                    #     int i = 0;
                    #     static int selected[16];
                    #     nk_layout_row_static(ctx, 18, 100, 1);
                    #     for (i = 0; i < 16; ++i)
                    #         nk_selectable_label(ctx, (selected[i]) ? "Selected": "Unselected", NK_TEXT_CENTERED, &selected[i]);
                    #     nk_group_end(ctx);
                    # }
                    # nk_tree_pop(ctx);

                    pynk.lib.nk_layout_row_static(ctx, self.group_height[0], self.group_width[0], 2);
                    if pynk.lib.nk_group_begin(ctx, "Group", group_flags):
                        self.declare("selected", [0]*16, "int[]")
                        pynk.lib.nk_layout_row_static(ctx, 18, 100, 1);
                        for i in xrange(16):
                            pynk.lib.nk_selectable_label(ctx, "Selected" if (self.selected[i]) else "Unselected", pynk.lib.NK_TEXT_CENTERED, self.selected+i);
                        pynk.lib.nk_group_end(ctx);
                    pynk.lib.nk_tree_pop(ctx);
                # }
                #
                # if (nk_tree_push(ctx, NK_TREE_NODE, "Notebook", NK_MINIMIZED))
                # {
                if self.tree_push(ctx, pynk.lib.NK_TREE_NODE, "Notebook", pynk.lib.NK_MINIMIZED, "16"):
                    # static int current_tab = 0;
                    # struct nk_vec2 item_padding;
                    # struct nk_rect bounds;
                    # float step = (2*3.141592654f) / 32;
                    # enum chart_type {CHART_LINE, CHART_HISTO, CHART_MIXED};
                    # const char *names[] = {"Lines", "Columns", "Mixed"};
                    # float id = 0;
                    # int i;
                    self.declare("current_tab", 0, "int*")
                    item_padding = pynk.ffi.new("struct nk_vec2*")
                    bounds = pynk.ffi.new("struct nk_rect*")
                    step = (2*3.141592654) / 32
                    CHART_LINE = 0
                    CHART_HISTO = 1
                    CHART_MIXED = 2
                    names = ["Lines", "Columns", "Mixed"]
                    id = 0

                    #
                    # /* Header */
                    # nk_style_push_vec2(ctx, &ctx->style.window.spacing, nk_vec2(0,0));
                    # nk_style_push_float(ctx, &ctx->style.button.rounding, 0);
                    # nk_layout_row_begin(ctx, NK_STATIC, 20, 3);
                    # for (i = 0; i < 3; ++i) {
                    #     /* make sure button perfectly fits text */
                    #     const struct nk_user_font *f = ctx->style.font;
                    #     float text_width = f->width(f->userdata, f->height, names[i], nk_strlen(names[i]));
                    #     float widget_width = text_width + 3 * ctx->style.button.padding.x;
                    #     nk_layout_row_push(ctx, widget_width);
                    #     if (current_tab == i) {
                    #         /* active tab gets highlighted */
                    #         struct nk_style_item button_color = ctx->style.button.normal;
                    #         ctx->style.button.normal = ctx->style.button.active;
                    #         current_tab = nk_button_label(ctx, names[i]) ? i: current_tab;
                    #         ctx->style.button.normal = button_color;
                    #     } else current_tab = nk_button_label(ctx, names[i]) ? i: current_tab;
                    # }
                    # nk_style_pop_float(ctx);
                    pynk.lib.nk_style_push_vec2(ctx, self.get_field_cdata(ctx, "style.window.spacing"), pynk.lib.nk_vec2(0,0));
                    pynk.lib.nk_style_push_float(ctx, self.get_field_cdata(ctx, "style.button.rounding"), 0);
                    pynk.lib.nk_layout_row_begin(ctx, pynk.lib.NK_STATIC, 20, 3);
                    for i in xrange(3):
                        #/* make sure button perfectly fits text */
                        f = ctx.style.font;
                        # TODO: cffi does not support passing unions by value so this won't work at present.
                        text_width = 100 #f.width(f.userdata, f.height, names[i], pynk.lib.nk_strlen(names[i]));
                        widget_width = text_width + 3 * ctx.style.button.padding.x;
                        pynk.lib.nk_layout_row_push(ctx, widget_width);
                        if self.current_tab[0] == i:
                            #/* active tab gets highlighted */
                            button_color = ctx.style.button.normal;
                            ctx.style.button.normal = ctx.style.button.active;
                            self.current_tab[0] = i if pynk.lib.nk_button_label(ctx, names[i]) else self.current_tab[0];
                            ctx.style.button.normal = button_color;
                        else:
                            self.current_tab[0] = i if pynk.lib.nk_button_label(ctx, names[i]) else self.current_tab[0];
                    pynk.lib.nk_style_pop_float(ctx);
                    #
                    # /* Body */
                    # nk_layout_row_dynamic(ctx, 140, 1);
                    # if (nk_group_begin(ctx, "Notebook", NK_WINDOW_BORDER))
                    # {
                    #     nk_style_pop_vec2(ctx);
                    #     switch (current_tab) {
                    #     case CHART_LINE:
                    #         nk_layout_row_dynamic(ctx, 100, 1);
                    #         bounds = nk_widget_bounds(ctx);
                    #         if (nk_chart_begin_colored(ctx, NK_CHART_LINES, nk_rgb(255,0,0), nk_rgb(150,0,0), 32, 0.0f, 1.0f)) {
                    #             nk_chart_add_slot_colored(ctx, NK_CHART_LINES, nk_rgb(0,0,255), nk_rgb(0,0,150),32, -1.0f, 1.0f);
                    #             for (i = 0, id = 0; i < 32; ++i) {
                    #                 nk_chart_push_slot(ctx, (float)fabs(sin(id)), 0);
                    #                 nk_chart_push_slot(ctx, (float)cos(id), 1);
                    #                 id += step;
                    #             }
                    #         }
                    #         nk_chart_end(ctx);
                    #         break;
                    #     case CHART_HISTO:
                    #         nk_layout_row_dynamic(ctx, 100, 1);
                    #         bounds = nk_widget_bounds(ctx);
                    #         if (nk_chart_begin_colored(ctx, NK_CHART_COLUMN, nk_rgb(255,0,0), nk_rgb(150,0,0), 32, 0.0f, 1.0f)) {
                    #             for (i = 0, id = 0; i < 32; ++i) {
                    #                 nk_chart_push_slot(ctx, (float)fabs(sin(id)), 0);
                    #                 id += step;
                    #             }
                    #         }
                    #         nk_chart_end(ctx);
                    #         break;
                    #     case CHART_MIXED:
                    #         nk_layout_row_dynamic(ctx, 100, 1);
                    #         bounds = nk_widget_bounds(ctx);
                    #         if (nk_chart_begin_colored(ctx, NK_CHART_LINES, nk_rgb(255,0,0), nk_rgb(150,0,0), 32, 0.0f, 1.0f)) {
                    #             nk_chart_add_slot_colored(ctx, NK_CHART_LINES, nk_rgb(0,0,255), nk_rgb(0,0,150),32, -1.0f, 1.0f);
                    #             nk_chart_add_slot_colored(ctx, NK_CHART_COLUMN, nk_rgb(0,255,0), nk_rgb(0,150,0), 32, 0.0f, 1.0f);
                    #             for (i = 0, id = 0; i < 32; ++i) {
                    #                 nk_chart_push_slot(ctx, (float)fabs(sin(id)), 0);
                    #                 nk_chart_push_slot(ctx, (float)fabs(cos(id)), 1);
                    #                 nk_chart_push_slot(ctx, (float)fabs(sin(id)), 2);
                    #                 id += step;
                    #             }
                    #         }
                    #         nk_chart_end(ctx);
                    #         break;
                    #     }
                    #     nk_group_end(ctx);
                    # } else nk_style_pop_vec2(ctx);
                    # nk_tree_pop(ctx);
                    pynk.lib.nk_layout_row_dynamic(ctx, 140, 1);
                    if pynk.lib.nk_group_begin(ctx, "Notebook", pynk.lib.NK_WINDOW_BORDER):
                        pynk.lib.nk_style_pop_vec2(ctx);
                        if self.current_tab[0] == CHART_LINE:
                            pynk.lib.nk_layout_row_dynamic(ctx, 100, 1);
                            bounds = pynk.lib.nk_widget_bounds(ctx);
                            if pynk.lib.nk_chart_begin_colored(ctx, pynk.lib.NK_CHART_LINES, pynk.lib.nk_rgb(255,0,0), pynk.lib.nk_rgb(150,0,0), 32, 0.0, 1.0):
                                pynk.lib.nk_chart_add_slot_colored(ctx, pynk.lib.NK_CHART_LINES, pynk.lib.nk_rgb(0,0,255), pynk.lib.nk_rgb(0,0,150),32, -1.0, 1.0);
                                id = 0
                                for i in xrange(32):
                                    pynk.lib.nk_chart_push_slot(ctx, math.fabs(math.sin(id)), 0);
                                    pynk.lib.nk_chart_push_slot(ctx, math.cos(id), 1);
                                    id += step;
                                pynk.lib.nk_chart_end(ctx);
                        elif self.current_tab[0] == CHART_HISTO:
                            pynk.lib.nk_layout_row_dynamic(ctx, 100, 1);
                            bounds = pynk.lib.nk_widget_bounds(ctx);
                            if pynk.lib.nk_chart_begin_colored(ctx, pynk.lib.NK_CHART_COLUMN, pynk.lib.nk_rgb(255,0,0), pynk.lib.nk_rgb(150,0,0), 32, 0.0, 1.0):
                                id = 0
                                for i in xrange(32):
                                    pynk.lib.nk_chart_push_slot(ctx, math.fabs(math.sin(id)), 0);
                                    id += step;
                                pynk.lib.nk_chart_end(ctx);
                        elif self.current_tab[0] == CHART_MIXED:
                            pynk.lib.nk_layout_row_dynamic(ctx, 100, 1);
                            bounds = pynk.lib.nk_widget_bounds(ctx);
                            if pynk.lib.nk_chart_begin_colored(ctx, pynk.lib.NK_CHART_LINES, pynk.lib.nk_rgb(255,0,0), pynk.lib.nk_rgb(150,0,0), 32, 0.0, 1.0):
                                pynk.lib.nk_chart_add_slot_colored(ctx, pynk.lib.NK_CHART_LINES, pynk.lib.nk_rgb(0,0,255), pynk.lib.nk_rgb(0,0,150),32, -1.0, 1.0);
                                pynk.lib.nk_chart_add_slot_colored(ctx, pynk.lib.NK_CHART_COLUMN, pynk.lib.nk_rgb(0,255,0), pynk.lib.nk_rgb(0,150,0), 32, 0.0, 1.0);
                                id = 0
                                for i in xrange(32):
                                    pynk.lib.nk_chart_push_slot(ctx, math.fabs(math.sin(id)), 0);
                                    pynk.lib.nk_chart_push_slot(ctx, math.fabs(math.cos(id)), 1);
                                    pynk.lib.nk_chart_push_slot(ctx, math.fabs(math.sin(id)), 2);
                                    id += step;
                            pynk.lib.nk_chart_end(ctx);
                        pynk.lib.nk_group_end(ctx);
                    else:
                        pynk.lib.nk_style_pop_vec2(ctx);
                    pynk.lib.nk_tree_pop(ctx);
                # }
                #
                # if (nk_tree_push(ctx, NK_TREE_NODE, "Simple", NK_MINIMIZED))
                # {
                if self.tree_push(ctx, pynk.lib.NK_TREE_NODE, "Simple", pynk.lib.NK_MINIMIZED, "17"):
                    # nk_layout_row_dynamic(ctx, 300, 2);
                    # if (nk_group_begin(ctx, "Group_Without_Border", 0)) {
                    #     int i = 0;
                    #     char buffer[64];
                    #     nk_layout_row_static(ctx, 18, 150, 1);
                    #     for (i = 0; i < 64; ++i) {
                    #         sprintf(buffer, "0x%02x", i);
                    #         nk_labelf(ctx, NK_TEXT_LEFT, "%s: scrollable region", buffer);
                    #     }
                    #     nk_group_end(ctx);
                    # }
                    # if (nk_group_begin(ctx, "Group_With_Border", NK_WINDOW_BORDER)) {
                    #     int i = 0;
                    #     char buffer[64];
                    #     nk_layout_row_dynamic(ctx, 25, 2);
                    #     for (i = 0; i < 64; ++i) {
                    #         sprintf(buffer, "%08d", ((((i%7)*10)^32))+(64+(i%2)*2));
                    #         nk_button_label(ctx, buffer);
                    #     }
                    #     nk_group_end(ctx);
                    # }
                    # nk_tree_pop(ctx);
                    pynk.lib.nk_layout_row_dynamic(ctx, 300, 2);
                    if pynk.lib.nk_group_begin(ctx, "Group_Without_Border", 0):
                        pynk.lib.nk_layout_row_static(ctx, 18, 150, 1);
                        for i in xrange(64):
                            pynk.lib.nk_labelf(ctx, pynk.lib.NK_TEXT_LEFT, "%s: scrollable region" % str(i));
                        pynk.lib.nk_group_end(ctx);
                    if pynk.lib.nk_group_begin(ctx, "Group_With_Border", pynk.lib.NK_WINDOW_BORDER):
                        pynk.lib.nk_layout_row_dynamic(ctx, 25, 2);
                        for i in xrange(64):
                            pynk.lib.nk_button_label(ctx, str(((((i%7)*10)^32))+(64+(i%2)*2)));
                        pynk.lib.nk_group_end(ctx);
                    pynk.lib.nk_tree_pop(ctx);
                # }
                #
                # if (nk_tree_push(ctx, NK_TREE_NODE, "Complex", NK_MINIMIZED))
                # {
                if self.tree_push(ctx, pynk.lib.NK_TREE_NODE, "Complex", pynk.lib.NK_MINIMIZED, "18"):
                    # int i;
                    # nk_layout_space_begin(ctx, NK_STATIC, 500, 64);
                    # nk_layout_space_push(ctx, nk_rect(0,0,150,500));
                    # if (nk_group_begin(ctx, "Group_left", NK_WINDOW_BORDER)) {
                    #     static int selected[32];
                    #     nk_layout_row_static(ctx, 18, 100, 1);
                    #     for (i = 0; i < 32; ++i)
                    #         nk_selectable_label(ctx, (selected[i]) ? "Selected": "Unselected", NK_TEXT_CENTERED, &selected[i]);
                    #     nk_group_end(ctx);
                    # }
                    pynk.lib.nk_layout_space_begin(ctx, pynk.lib.NK_STATIC, 500, 64);
                    pynk.lib.nk_layout_space_push(ctx, pynk.lib.nk_rect(0,0,150,500));
                    if pynk.lib.nk_group_begin(ctx, "Group_left", pynk.lib.NK_WINDOW_BORDER):
                        self.declare("selected", [0]*32, "int[]")
                        pynk.lib.nk_layout_row_static(ctx, 18, 100, 1);
                        for i in xrange(32):
                            pynk.lib.nk_selectable_label(ctx, "Selected" if self.selected[i] else "Unselected", pynk.lib.NK_TEXT_CENTERED, self.selected+i);
                        pynk.lib.nk_group_end(ctx);
                    #
                    # nk_layout_space_push(ctx, nk_rect(160,0,150,240));
                    # if (nk_group_begin(ctx, "Group_top", NK_WINDOW_BORDER)) {
                    #     nk_layout_row_dynamic(ctx, 25, 1);
                    #     nk_button_label(ctx, "#FFAA");
                    #     nk_button_label(ctx, "#FFBB");
                    #     nk_button_label(ctx, "#FFCC");
                    #     nk_button_label(ctx, "#FFDD");
                    #     nk_button_label(ctx, "#FFEE");
                    #     nk_button_label(ctx, "#FFFF");
                    #     nk_group_end(ctx);
                    # }
                    pynk.lib.nk_layout_space_push(ctx, pynk.lib.nk_rect(160,0,150,240));
                    if pynk.lib.nk_group_begin(ctx, "Group_top", pynk.lib.NK_WINDOW_BORDER):
                        pynk.lib.nk_layout_row_dynamic(ctx, 25, 1);
                        pynk.lib.nk_button_label(ctx, "#FFAA");
                        pynk.lib.nk_button_label(ctx, "#FFBB");
                        pynk.lib.nk_button_label(ctx, "#FFCC");
                        pynk.lib.nk_button_label(ctx, "#FFDD");
                        pynk.lib.nk_button_label(ctx, "#FFEE");
                        pynk.lib.nk_button_label(ctx, "#FFFF");
                        pynk.lib.nk_group_end(ctx);
                    #
                    # nk_layout_space_push(ctx, nk_rect(160,250,150,250));
                    # if (nk_group_begin(ctx, "Group_buttom", NK_WINDOW_BORDER)) {
                    #     nk_layout_row_dynamic(ctx, 25, 1);
                    #     nk_button_label(ctx, "#FFAA");
                    #     nk_button_label(ctx, "#FFBB");
                    #     nk_button_label(ctx, "#FFCC");
                    #     nk_button_label(ctx, "#FFDD");
                    #     nk_button_label(ctx, "#FFEE");
                    #     nk_button_label(ctx, "#FFFF");
                    #     nk_group_end(ctx);
                    # }
                    pynk.lib.nk_layout_space_push(ctx, pynk.lib.nk_rect(160,250,150,250));
                    if pynk.lib.nk_group_begin(ctx, "Group_buttom", pynk.lib.NK_WINDOW_BORDER):
                        pynk.lib.nk_layout_row_dynamic(ctx, 25, 1);
                        pynk.lib.nk_button_label(ctx, "#FFAA");
                        pynk.lib.nk_button_label(ctx, "#FFBB");
                        pynk.lib.nk_button_label(ctx, "#FFCC");
                        pynk.lib.nk_button_label(ctx, "#FFDD");
                        pynk.lib.nk_button_label(ctx, "#FFEE");
                        pynk.lib.nk_button_label(ctx, "#FFFF");
                        pynk.lib.nk_group_end(ctx);
                    #
                    # nk_layout_space_push(ctx, nk_rect(320,0,150,150));
                    # if (nk_group_begin(ctx, "Group_right_top", NK_WINDOW_BORDER)) {
                    #     static int selected[4];
                    #     nk_layout_row_static(ctx, 18, 100, 1);
                    #     for (i = 0; i < 4; ++i)
                    #         nk_selectable_label(ctx, (selected[i]) ? "Selected": "Unselected", NK_TEXT_CENTERED, &selected[i]);
                    #     nk_group_end(ctx);
                    # }
                    pynk.lib.nk_layout_space_push(ctx, pynk.lib.nk_rect(320,0,150,150));
                    if pynk.lib.nk_group_begin(ctx, "Group_right_top", pynk.lib.NK_WINDOW_BORDER):
                        self.declare("selected", [0]*4, "int[]")
                        pynk.lib.nk_layout_row_static(ctx, 18, 100, 1);
                        for i in xrange(4):
                            pynk.lib.nk_selectable_label(ctx, "Selected" if self.selected[i] else "Unselected", pynk.lib.NK_TEXT_CENTERED, self.selected+i);
                        pynk.lib.nk_group_end(ctx);
                    #
                    # nk_layout_space_push(ctx, nk_rect(320,160,150,150));
                    # if (nk_group_begin(ctx, "Group_right_center", NK_WINDOW_BORDER)) {
                    #     static int selected[4];
                    #     nk_layout_row_static(ctx, 18, 100, 1);
                    #     for (i = 0; i < 4; ++i)
                    #         nk_selectable_label(ctx, (selected[i]) ? "Selected": "Unselected", NK_TEXT_CENTERED, &selected[i]);
                    #     nk_group_end(ctx);
                    # }
                    pynk.lib.nk_layout_space_push(ctx, pynk.lib.nk_rect(320,160,150,150));
                    if pynk.lib.nk_group_begin(ctx, "Group_right_center", pynk.lib.NK_WINDOW_BORDER):
                        self.declare("selected", [0]*4, "int[]")
                        pynk.lib.nk_layout_row_static(ctx, 18, 100, 1);
                        for i in xrange(4):
                            pynk.lib.nk_selectable_label(ctx, "Selected" if self.selected[i] else "Unselected", pynk.lib.NK_TEXT_CENTERED, self.selected+i);
                        pynk.lib.nk_group_end(ctx);
                    #
                    # nk_layout_space_push(ctx, nk_rect(320,320,150,150));
                    # if (nk_group_begin(ctx, "Group_right_bottom", NK_WINDOW_BORDER)) {
                    #     static int selected[4];
                    #     nk_layout_row_static(ctx, 18, 100, 1);
                    #     for (i = 0; i < 4; ++i)
                    #         nk_selectable_label(ctx, (selected[i]) ? "Selected": "Unselected", NK_TEXT_CENTERED, &selected[i]);
                    #     nk_group_end(ctx);
                    # }
                    # nk_layout_space_end(ctx);
                    # nk_tree_pop(ctx);
                    pynk.lib.nk_layout_space_push(ctx, pynk.lib.nk_rect(320,320,150,150));
                    if pynk.lib.nk_group_begin(ctx, "Group_right_bottom", pynk.lib.NK_WINDOW_BORDER):
                        self.declare("selected", [0]*4, "int[]")
                        pynk.lib.nk_layout_row_static(ctx, 18, 100, 1);
                        for i in xrange(4):
                            pynk.lib.nk_selectable_label(ctx, "Selected" if self.selected[i] else "Unselected", pynk.lib.NK_TEXT_CENTERED, self.selected+i);
                        pynk.lib.nk_group_end(ctx);
                    pynk.lib.nk_layout_space_end(ctx);
                    pynk.lib.nk_tree_pop(ctx);
                # }
                #
                # if (nk_tree_push(ctx, NK_TREE_NODE, "Splitter", NK_MINIMIZED))
                # {
                if self.tree_push(ctx, pynk.lib.NK_TREE_NODE, "Splitter", pynk.lib.NK_MINIMIZED, "20"):
                    # const struct nk_input *in = &ctx->input;
                    # nk_layout_row_static(ctx, 20, 320, 1);
                    # nk_label(ctx, "Use slider and spinner to change tile size", NK_TEXT_LEFT);
                    # nk_label(ctx, "Drag the space between tiles to change tile ratio", NK_TEXT_LEFT);
                    pynk.lib.nk_layout_row_static(ctx, 20, 320, 1);
                    pynk.lib.nk_label(ctx, "Use slider and spinner to change tile size", pynk.lib.NK_TEXT_LEFT);
                    pynk.lib.nk_label(ctx, "Drag the space between tiles to change tile ratio", pynk.lib.NK_TEXT_LEFT);
                    #
                    # if (nk_tree_push(ctx, NK_TREE_NODE, "Vertical", NK_MINIMIZED))
                    # {
                    if self.tree_push(ctx, pynk.lib.NK_TREE_NODE, "Vertical", pynk.lib.NK_MINIMIZED, "21"):
                        # static float a = 100, b = 100, c = 100;
                        self.declare("a", 100, "float*")
                        self.declare("b", 100, "float*")
                        self.declare("c", 100, "float*")

                        # struct nk_rect bounds;
                        #
                        # float row_layout[5];
                        # row_layout[0] = a;
                        # row_layout[1] = 8;
                        # row_layout[2] = b;
                        # row_layout[3] = 8;
                        # row_layout[4] = c;
                        bounds = pynk.ffi.new("struct nk_rect*")
                        row_layout = pynk.ffi.new("float[5]")
                        row_layout[0] = self.a[0];
                        row_layout[1] = 8;
                        row_layout[2] = self.b[0];
                        row_layout[3] = 8;
                        row_layout[4] = self.c[0];
                        #
                        # /* header */
                        # nk_layout_row_static(ctx, 30, 100, 2);
                        # nk_label(ctx, "left:", NK_TEXT_LEFT);
                        # nk_slider_float(ctx, 10.0f, &a, 200.0f, 10.0f);
                        #
                        # nk_label(ctx, "middle:", NK_TEXT_LEFT);
                        # nk_slider_float(ctx, 10.0f, &b, 200.0f, 10.0f);
                        #
                        # nk_label(ctx, "right:", NK_TEXT_LEFT);
                        # nk_slider_float(ctx, 10.0f, &c, 200.0f, 10.0f);

                        pynk.lib.nk_layout_row_static(ctx, 30, 100, 2);
                        pynk.lib.nk_label(ctx, "left:", pynk.lib.NK_TEXT_LEFT);
                        pynk.lib.nk_slider_float(ctx, 10.0, self.a, 200.0, 10.0);
                        pynk.lib.nk_label(ctx, "middle:", pynk.lib.NK_TEXT_LEFT);
                        pynk.lib.nk_slider_float(ctx, 10.0, self.b, 200.0, 10.0);
                        pynk.lib.nk_label(ctx, "right:", pynk.lib.NK_TEXT_LEFT);
                        pynk.lib.nk_slider_float(ctx, 10.0, self.c, 200.0, 10.0);



                        # /* tiles */
                        # nk_layout_row(ctx, NK_STATIC, 200, 5, row_layout);
                        pynk.lib.nk_layout_row(ctx, pynk.lib.NK_STATIC, 200, 5, row_layout);
                        #
                        # /* left space */
                        # if (nk_group_begin(ctx, "left", NK_WINDOW_NO_SCROLLBAR|NK_WINDOW_BORDER|NK_WINDOW_NO_SCROLLBAR)) {
                        #     nk_layout_row_dynamic(ctx, 25, 1);
                        #     nk_button_label(ctx, "#FFAA");
                        #     nk_button_label(ctx, "#FFBB");
                        #     nk_button_label(ctx, "#FFCC");
                        #     nk_button_label(ctx, "#FFDD");
                        #     nk_button_label(ctx, "#FFEE");
                        #     nk_button_label(ctx, "#FFFF");
                        #     nk_group_end(ctx);
                        # }
                        if pynk.lib.nk_group_begin(ctx, "left", pynk.lib.NK_WINDOW_NO_SCROLLBAR|pynk.lib.NK_WINDOW_BORDER|pynk.lib.NK_WINDOW_NO_SCROLLBAR):
                            pynk.lib.nk_layout_row_dynamic(ctx, 25, 1);
                            pynk.lib.nk_button_label(ctx, "#FFAA");
                            pynk.lib.nk_button_label(ctx, "#FFBB");
                            pynk.lib.nk_button_label(ctx, "#FFCC");
                            pynk.lib.nk_button_label(ctx, "#FFDD");
                            pynk.lib.nk_button_label(ctx, "#FFEE");
                            pynk.lib.nk_button_label(ctx, "#FFFF");
                            pynk.lib.nk_group_end(ctx);
                        #
                        # /* scaler */
                        # bounds = nk_widget_bounds(ctx);
                        # nk_spacing(ctx, 1);
                        # if ((nk_input_is_mouse_hovering_rect(in, bounds) ||
                        #     nk_input_is_mouse_prev_hovering_rect(in, bounds)) &&
                        #     nk_input_is_mouse_down(in, NK_BUTTON_LEFT))
                        # {
                        #     a = row_layout[0] + in->mouse.delta.x;
                        #     b = row_layout[2] - in->mouse.delta.x;
                        # }
                        ipt = self.get_field_cdata(ctx, "input")
                        bounds = pynk.lib.nk_widget_bounds(ctx);
                        pynk.lib.nk_spacing(ctx, 1);
                        if (pynk.lib.nk_input_is_mouse_hovering_rect(ipt, bounds) or
                                pynk.lib.nk_input_is_mouse_prev_hovering_rect(ipt, bounds)) and \
                                pynk.lib.nk_input_is_mouse_down(ipt, pynk.lib.NK_BUTTON_LEFT):
                            self.a[0] = row_layout[0] + ipt.mouse.delta.x;
                            self.b[0] = row_layout[2] - ipt.mouse.delta.x;
                        #
                        # /* middle space */
                        # if (nk_group_begin(ctx, "center", NK_WINDOW_BORDER|NK_WINDOW_NO_SCROLLBAR)) {
                        #     nk_layout_row_dynamic(ctx, 25, 1);
                        #     nk_button_label(ctx, "#FFAA");
                        #     nk_button_label(ctx, "#FFBB");
                        #     nk_button_label(ctx, "#FFCC");
                        #     nk_button_label(ctx, "#FFDD");
                        #     nk_button_label(ctx, "#FFEE");
                        #     nk_button_label(ctx, "#FFFF");
                        #     nk_group_end(ctx);
                        # }
                        if pynk.lib.nk_group_begin(ctx, "center", pynk.lib.NK_WINDOW_BORDER|pynk.lib.NK_WINDOW_NO_SCROLLBAR):
                            pynk.lib.nk_layout_row_dynamic(ctx, 25, 1);
                            pynk.lib.nk_button_label(ctx, "#FFAA");
                            pynk.lib.nk_button_label(ctx, "#FFBB");
                            pynk.lib.nk_button_label(ctx, "#FFCC");
                            pynk.lib.nk_button_label(ctx, "#FFDD");
                            pynk.lib.nk_button_label(ctx, "#FFEE");
                            pynk.lib.nk_button_label(ctx, "#FFFF");
                            pynk.lib.nk_group_end(ctx);
                        #
                        # /* scaler */
                        # bounds = nk_widget_bounds(ctx);
                        # nk_spacing(ctx, 1);
                        # if ((nk_input_is_mouse_hovering_rect(in, bounds) ||
                        #     nk_input_is_mouse_prev_hovering_rect(in, bounds)) &&
                        #     nk_input_is_mouse_down(in, NK_BUTTON_LEFT))
                        # {
                        #     b = (row_layout[2] + in->mouse.delta.x);
                        #     c = (row_layout[4] - in->mouse.delta.x);
                        # }
                        bounds = pynk.lib.nk_widget_bounds(ctx);
                        pynk.lib.nk_spacing(ctx, 1);
                        if (pynk.lib.nk_input_is_mouse_hovering_rect(ipt, bounds) or
                                pynk.lib.nk_input_is_mouse_prev_hovering_rect(ipt, bounds)) and \
                                pynk.lib.nk_input_is_mouse_down(ipt, pynk.lib.NK_BUTTON_LEFT):
                            self.b[0] = (row_layout[2] + ipt.mouse.delta.x);
                            self.c[0] = (row_layout[4] - ipt.mouse.delta.x);
                        #
                        # /* right space */
                        # if (nk_group_begin(ctx, "right", NK_WINDOW_BORDER|NK_WINDOW_NO_SCROLLBAR)) {
                        #     nk_layout_row_dynamic(ctx, 25, 1);
                        #     nk_button_label(ctx, "#FFAA");
                        #     nk_button_label(ctx, "#FFBB");
                        #     nk_button_label(ctx, "#FFCC");
                        #     nk_button_label(ctx, "#FFDD");
                        #     nk_button_label(ctx, "#FFEE");
                        #     nk_button_label(ctx, "#FFFF");
                        #     nk_group_end(ctx);
                        # }
                        #
                        # nk_tree_pop(ctx);
                        if pynk.lib.nk_group_begin(ctx, "right", pynk.lib.NK_WINDOW_BORDER|pynk.lib.NK_WINDOW_NO_SCROLLBAR):
                            pynk.lib.nk_layout_row_dynamic(ctx, 25, 1);
                            pynk.lib.nk_button_label(ctx, "#FFAA");
                            pynk.lib.nk_button_label(ctx, "#FFBB");
                            pynk.lib.nk_button_label(ctx, "#FFCC");
                            pynk.lib.nk_button_label(ctx, "#FFDD");
                            pynk.lib.nk_button_label(ctx, "#FFEE");
                            pynk.lib.nk_button_label(ctx, "#FFFF");
                            pynk.lib.nk_group_end(ctx);
                        pynk.lib.nk_tree_pop(ctx);
                    # }
                    #
                    # if (nk_tree_push(ctx, NK_TREE_NODE, "Horizontal", NK_MINIMIZED))
                    # {
                    if self.tree_push(ctx, pynk.lib.NK_TREE_NODE, "Horizontal", pynk.lib.NK_MINIMIZED, "24"):
                        # static float a = 100, b = 100, c = 100;
                        self.declare("a", 100, "float*")
                        self.declare("b", 100, "float*")
                        self.declare("c", 100, "float*")
                        # struct nk_rect bounds;
                        bounds = pynk.ffi.new("struct nk_rect*")
                        #
                        # /* header */
                        # nk_layout_row_static(ctx, 30, 100, 2);
                        # nk_label(ctx, "top:", NK_TEXT_LEFT);
                        # nk_slider_float(ctx, 10.0f, &a, 200.0f, 10.0f);
                        #
                        # nk_label(ctx, "middle:", NK_TEXT_LEFT);
                        # nk_slider_float(ctx, 10.0f, &b, 200.0f, 10.0f);
                        #
                        # nk_label(ctx, "bottom:", NK_TEXT_LEFT);
                        # nk_slider_float(ctx, 10.0f, &c, 200.0f, 10.0f);
                        pynk.lib.nk_layout_row_static(ctx, 30, 100, 2);
                        pynk.lib.nk_label(ctx, "top:", pynk.lib.NK_TEXT_LEFT);
                        pynk.lib.nk_slider_float(ctx, 10.0, self.a, 200.0, 10.0);
                        pynk.lib.nk_label(ctx, "middle:", pynk.lib.NK_TEXT_LEFT);
                        pynk.lib.nk_slider_float(ctx, 10.0, self.b, 200.0, 10.0);
                        pynk.lib.nk_label(ctx, "bottom:", pynk.lib.NK_TEXT_LEFT);
                        pynk.lib.nk_slider_float(ctx, 10.0, self.c, 200.0, 10.0);
                        #
                        # /* top space */
                        # nk_layout_row_dynamic(ctx, a, 1);
                        # if (nk_group_begin(ctx, "top", NK_WINDOW_NO_SCROLLBAR|NK_WINDOW_BORDER)) {
                        #     nk_layout_row_dynamic(ctx, 25, 3);
                        #     nk_button_label(ctx, "#FFAA");
                        #     nk_button_label(ctx, "#FFBB");
                        #     nk_button_label(ctx, "#FFCC");
                        #     nk_button_label(ctx, "#FFDD");
                        #     nk_button_label(ctx, "#FFEE");
                        #     nk_button_label(ctx, "#FFFF");
                        #     nk_group_end(ctx);
                        # }
                        pynk.lib.nk_layout_row_dynamic(ctx, self.a[0], 1);
                        if pynk.lib.nk_group_begin(ctx, "top", pynk.lib.NK_WINDOW_NO_SCROLLBAR|pynk.lib.NK_WINDOW_BORDER):
                            pynk.lib.nk_layout_row_dynamic(ctx, 25, 3);
                            pynk.lib.nk_button_label(ctx, "#FFAA");
                            pynk.lib.nk_button_label(ctx, "#FFBB");
                            pynk.lib.nk_button_label(ctx, "#FFCC");
                            pynk.lib.nk_button_label(ctx, "#FFDD");
                            pynk.lib.nk_button_label(ctx, "#FFEE");
                            pynk.lib.nk_button_label(ctx, "#FFFF");
                            pynk.lib.nk_group_end(ctx);

                        #
                        # /* scaler */
                        # nk_layout_row_dynamic(ctx, 8, 1);
                        # bounds = nk_widget_bounds(ctx);
                        # nk_spacing(ctx, 1);
                        # if ((nk_input_is_mouse_hovering_rect(in, bounds) ||
                        #     nk_input_is_mouse_prev_hovering_rect(in, bounds)) &&
                        #     nk_input_is_mouse_down(in, NK_BUTTON_LEFT))
                        # {
                        #     a = a + in->mouse.delta.y;
                        #     b = b - in->mouse.delta.y;
                        # }
                        pynk.lib.nk_layout_row_dynamic(ctx, 8, 1)
                        bounds = pynk.lib.nk_widget_bounds(ctx);
                        pynk.lib.nk_spacing(ctx, 1);
                        ipt = self.get_field_cdata(ctx, "input")
                        if (pynk.lib.nk_input_is_mouse_hovering_rect(
                                ipt, bounds) or
                                pynk.lib.nk_input_is_mouse_prev_hovering_rect(
                                    ipt, bounds)) and \
                                pynk.lib.nk_input_is_mouse_down(ipt,
                                                                pynk.lib.NK_BUTTON_LEFT):
                            self.a[0] = self.a[0] + ipt.mouse.delta.y;
                            self.b[0] = self.b[0] - ipt.mouse.delta.y;
                        #
                        #
                        # /* middle space */
                        # nk_layout_row_dynamic(ctx, b, 1);
                        # if (nk_group_begin(ctx, "middle", NK_WINDOW_NO_SCROLLBAR|NK_WINDOW_BORDER)) {
                        #     nk_layout_row_dynamic(ctx, 25, 3);
                        #     nk_button_label(ctx, "#FFAA");
                        #     nk_button_label(ctx, "#FFBB");
                        #     nk_button_label(ctx, "#FFCC");
                        #     nk_button_label(ctx, "#FFDD");
                        #     nk_button_label(ctx, "#FFEE");
                        #     nk_button_label(ctx, "#FFFF");
                        #     nk_group_end(ctx);
                        # }
                        pynk.lib.nk_layout_row_dynamic(ctx, self.b[0], 1)
                        if pynk.lib.nk_group_begin(ctx, "middle", pynk.lib.NK_WINDOW_NO_SCROLLBAR|pynk.lib.NK_WINDOW_BORDER):
                            pynk.lib.nk_layout_row_dynamic(ctx, 25, 3);
                            pynk.lib.nk_button_label(ctx, "#FFAA");
                            pynk.lib.nk_button_label(ctx, "#FFBB");
                            pynk.lib.nk_button_label(ctx, "#FFCC");
                            pynk.lib.nk_button_label(ctx, "#FFDD");
                            pynk.lib.nk_button_label(ctx, "#FFEE");
                            pynk.lib.nk_button_label(ctx, "#FFFF");
                            pynk.lib.nk_group_end(ctx);
                        #
                        # {
                        #     /* scaler */
                        #     nk_layout_row_dynamic(ctx, 8, 1);
                        #     bounds = nk_widget_bounds(ctx);
                        #     if ((nk_input_is_mouse_hovering_rect(in, bounds) ||
                        #         nk_input_is_mouse_prev_hovering_rect(in, bounds)) &&
                        #         nk_input_is_mouse_down(in, NK_BUTTON_LEFT))
                        #     {
                        #         b = b + in->mouse.delta.y;
                        #         c = c - in->mouse.delta.y;
                        #     }
                        # }
                        pynk.lib.nk_layout_row_dynamic(ctx, 8, 1)
                        bounds = pynk.lib.nk_widget_bounds(ctx)
                        if (pynk.lib.nk_input_is_mouse_hovering_rect(ipt, bounds) or
                                pynk.lib.nk_input_is_mouse_prev_hovering_rect(ipt, bounds)) and \
                                pynk.lib.nk_input_is_mouse_down(ipt, pynk.lib.NK_BUTTON_LEFT):
                            self.b[0] = self.b[0] + ipt.mouse.delta.y;
                            self.c[0] = self.c[0] - ipt.mouse.delta.y;
                        #
                        # /* bottom space */
                        # nk_layout_row_dynamic(ctx, c, 1);
                        # if (nk_group_begin(ctx, "bottom", NK_WINDOW_NO_SCROLLBAR|NK_WINDOW_BORDER)) {
                        #     nk_layout_row_dynamic(ctx, 25, 3);
                        #     nk_button_label(ctx, "#FFAA");
                        #     nk_button_label(ctx, "#FFBB");
                        #     nk_button_label(ctx, "#FFCC");
                        #     nk_button_label(ctx, "#FFDD");
                        #     nk_button_label(ctx, "#FFEE");
                        #     nk_button_label(ctx, "#FFFF");
                        #     nk_group_end(ctx);
                        # }
                        # nk_tree_pop(ctx);
                        pynk.lib.nk_layout_row_dynamic(ctx, self.c[0], 1)
                        if pynk.lib.nk_group_begin(ctx, "bottom", pynk.lib.NK_WINDOW_NO_SCROLLBAR|pynk.lib.NK_WINDOW_BORDER):
                            pynk.lib.nk_layout_row_dynamic(ctx, 25, 3);
                            pynk.lib.nk_button_label(ctx, "#FFAA");
                            pynk.lib.nk_button_label(ctx, "#FFBB");
                            pynk.lib.nk_button_label(ctx, "#FFCC");
                            pynk.lib.nk_button_label(ctx, "#FFDD");
                            pynk.lib.nk_button_label(ctx, "#FFEE");
                            pynk.lib.nk_button_label(ctx, "#FFFF");
                            pynk.lib.nk_group_end(ctx);
                        pynk.lib.nk_tree_pop(ctx)
                    # }
                    # nk_tree_pop(ctx);
                    pynk.lib.nk_tree_pop(ctx)
                # }
                # nk_tree_pop(ctx);
                pynk.lib.nk_tree_pop(ctx);
            # }
        # }
        # nk_end(ctx);
        # return !nk_window_is_closed(ctx, "Overview");
        pynk.lib.nk_end(ctx)
        return not pynk.lib.nk_window_is_closed(ctx, "PyOverview")
    # }