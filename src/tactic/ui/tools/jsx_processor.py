#!/usr/bin/python

__all__ = ["BaseReactWdg", "JSXTranspile"]

import tacticenv
from pyasm.common import Xml, Config, GlobalContainer, Container
from pyasm.web import DivWdg

from tactic.ui.common import BaseRefreshWdg

from subprocess import Popen, PIPE

import os, sys




class JSXTranspile():


    def process_jsx(cls, behavior):
        '''This method is used in the custom LayoutEditor which
        will take jsx in a behavior xml and produce the appropariate js'''

        jsxs = []
        behaviors = []

        # process the jsx
        test = "<jsx>%s</jsx>" % behavior
        xml = Xml()
        xml.read_string(test)
        items = xml.get_nodes("jsx/behavior")
        for item in items:

            attributes = xml.get_attributes(item)
            attributes_str = ""
            for name, value in attributes.items():
                attributes_str += '''%s="%s" ''' % (name, value)
            attributes_str = attributes_str.strip()


            try:
                jsx = xml.get_node_value(item)

                js = cls.transpile(jsx)

            except Exception as e:
                print("WARNING: ", e)
                js = None


            # store the original behaviors as jsx
            behavior = "<jsx %s><![CDATA[\n%s\n]]></jsx>" % (attributes_str, jsx)
            jsxs.append(behavior)

            if js:
                behavior = "<behavior %s><![CDATA[\n%s\n]]></behavior>" % (attributes_str, js)
                behaviors.append(behavior)


        behaviors_str = "\n".join(behaviors)
        jsxs_str = "\n".join(jsxs)

        return (behaviors_str, jsxs_str)

    process_jsx = classmethod(process_jsx)




    def transpile(cls, jsx):
        '''Method to transpile jsx to js'''

        executable = __file__
        python = Config.get_value("services", "python") or "python"

        cmds = [python, executable, "-f", "temp"]

        if isinstance(jsx, str):
            jsx = jsx.encode()


        from subprocess import Popen, PIPE
        p = Popen(cmds, stdin=PIPE, stdout=PIPE, stderr=PIPE)

        (o, e) = p.communicate(input=jsx)
        o = o.strip()
        e = e.strip()
        if e:
            e = e.decode()
            raise Exception(e)

        if jsx and not o:
            raise Exception("No compiled code")

        return o.decode()
    transpile = classmethod(transpile)



    def cache_jsx(cls, jsx_path, jsx=None, top=None):
        '''Onload JSX with caching'''

        tactic_mode = os.environ.get('TACTIC_MODE') or "development"
        is_dev_mode = False
        if tactic_mode == "development":
            is_dev_mode = True



        cache_key = "jsx:%s" % jsx_path


        # store this somewhere
        basename, ext = os.path.splitext(jsx_path)
        js_path = "%s.js" % basename


        js = None
        if is_dev_mode:
            if os.path.exists(js_path):

                js_time = os.path.getmtime(js_path)
                jsx_time = os.path.getmtime(jsx_path)

                if js_time - jsx_time > 0:
                    f = open(js_path, "r")
                    js = f.read()
                    f.close()


        else:
            js = GlobalContainer.get(cache_key)
            if js == None:
                # production mode always reads from file first time as there
                # likely is no jsx processor
                f = open(js_path, "r")
                js = f.read()
                f.close()

                GlobalContainer.put(cache_key, js)


        if js == None:

            from tactic.ui.tools import JSXTranspile

            if not jsx:

                f = open(jsx_path, "r")
                jsx = f.read()
                f.close()

            # transpile the jsx into js
            if is_dev_mode:
                try:
                    js = JSXTranspile.transpile(jsx)
                except Exception as e:
                    # if transpile fails, then try to read the js file
                    # (for those who do not have a JSX processor
                    message = str(e).replace("\\n", "\n")

                    lines = message.split("\n")
                    if lines[-1] == "Exception: Babel is not installed":
                        print("WARNING: Babel is not installed")
                        f = open(js_path, "r")
                        js = f.read()
                        f.close()
                    else:
                        print("Error transpiling: ", jsx_path)
                        print(message)
                        raise


                else:
                    print("Compiled JSX." )
                    f = open(js_path, "w")
                    f.write(js)
                    f.close()
                    print("Saved %s" % js_path )

            else:
                raise Exception("No corresponding js file found for jsx")

            GlobalContainer.put(cache_key, js)

        if top:
            top.add_behavior( {
                'type': 'load',
                'cbjs_action': js
            } )

        return js

    cache_jsx = classmethod(cache_jsx)







    def main(cls, text):
        '''method that is run from the command line in Popen above'''

        # Need this to get the environment right.
        # FIXME: hard coded
        # FIXME: there must be a better way to set the environment of node.js

        install_dir = tacticenv.get_install_dir()

        dirname = Config.get_value("jsx", "babel")
        if not dirname:
            dirname = "%s/3rd_party/babel" % install_dir

        if not os.path.exists(dirname):
            raise Exception("Babel is not installed")

        os.chdir(dirname)

        if isinstance(text, str):
            text = text.encode()


        executable = "%s/node_modules/.bin/babel" % dirname
        if not os.path.exists(executable):
            raise Exception("Babel is not installed")

        cmds = [executable, "-f", "temp", "--no-comments"]
        minified = False
        if minified:
            cmds.append("--compact")
            cmds.append("--minified")
        #cmds.append("--plugins")
        #cmds.append("babel-plugin-anonymize")
        p = Popen(cmds, stdin=PIPE, stdout=PIPE, stderr=PIPE)

        (o, e) = p.communicate(input=text)
        if e:
            decode = e.decode()
            if decode.startswith("Browserslist:"):
                decode = "\n".join( decode.split("\n")[3:] )
            if decode:
                sys.stderr.write(decode)

        return o.decode()
    main = classmethod(main)





class BaseReactWdg(BaseRefreshWdg):

    @classmethod
    def init_react(cls, top, jsx_path):

        f = open(jsx_path, "r")
        jsx = f.read()
        f.close()

        js_div = DivWdg()

        #
        # This code needs to move to JSX transpiler
        #
        try:
            js = JSXTranspile.cache_jsx(jsx_path, jsx)
        except Exception as e:
            error_div = DivWdg()
            top.add(error_div)
            error_div.add_style("margin: 20px")
            error_div.add_style("padding: 20px")
            error_div.add("<pre>%s</pre>" % e)

            return


        js = "if (!spt.react) { spt.react = {}; }\n\n" + js


        js_div.add_behavior( {
            'type': 'load',
            'cbjs_action': js
        } )



        # An atttempt not to use the whole behavior system just to load react
        """
        if Container.get("react_init") != True:
            js_div.add('''
            <script src="/plugins/unpkg/material-ui.production.min.js?ver=5.0.0.a02" ></script>
            <script src="/plugins/unpkg/react-router-dom.min.js?ver=5.0.0.a02" ></script>
            <script>
                var spt;
                if (!spt) spt = {};
            </script>
            ''');
            top.add(js_div)
            Container.put("react_init", True)


        js = "if (!spt.react) { spt.react = {}; }\n\n" + js
        import random
        f = "x" + str(random.randint(0, 10000000))
        js_div.add('''
        <script src="/plugins/unpkg/material-ui.production.min.js?ver=5.0.0.a02" ></script>
        <script src="/plugins/unpkg/react-router-dom.min.js?ver=5.0.0.a02" ></script>
        <script>
        let %s = function() {
            %s
        }
        %s();
        </script>
        ''' % (f, js, f) )
        """



        top.add(js_div)




    def get_react_wdg(self, class_name, props):
        react_wdg = DivWdg()
        react_wdg.add_behavior( {
            'type': 'load',
            'props': props,
            'cls': class_name,
            'cbjs_action': '''

            let cls_name = "spt.react." + bvr.cls;

            let cls;
            try {
                cls = eval(cls_name);
            }
            catch(e) {
                alert("ERROR: " + e);
                return;
            }

            if (!cls) {
                throw( bvr.cls + " does not exist");
            }


            let el = React.createElement(cls, bvr.props);

            // React 18
            let container = bvr.src_el;
            container.addClass("spt_react");

            const root = ReactDOM.createRoot(container);
            container.react_root = root;
            container.react_element = el;
            root.render(el);

            // React 17
            /*
            let react = ReactDOM.render(el, bvr.src_el);
            bvr.src_el.react = react;
            bvr.src_el.addClass("spt_react");
            */
            '''
        } )

        return react_wdg


    def get_onload_jsx(self):
        return ''





if __name__ == "__main__":

    # read from stdin
    text = sys.stdin.read()
    js = JSXTranspile.main(text)
    # output to stdout
    print(js)
