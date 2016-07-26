from gi.repository import Gtk


def error_message(parentwindow, message, reason=None):
    md = Gtk.MessageDialog(parent=parentwindow,
                           flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.USE_HEADER_BAR,
                           type=Gtk.MessageType.INFO,
                           buttons=Gtk.ButtonsType.OK, message_format=message)
    if reason is not None:
        md.format_secondary_text('Reason: ' + reason)
    result = md.run()
    md.destroy()
    return result


def question_message(parentwindow, question, detail=None):
    md = Gtk.MessageDialog(parent=parentwindow,
                           flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.USE_HEADER_BAR,
                           type=Gtk.MessageType.QUESTION,
                           buttons=Gtk.ButtonsType.YES_NO, message_format=question)
    if detail is not None:
        md.format_secondary_text(detail)
    result = md.run()
    md.destroy()
    return result == Gtk.ResponseType.YES


def info_message(parentwindow, info, detail=None):
    md = Gtk.MessageDialog(parent=parentwindow,
                           flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.USE_HEADER_BAR,
                           type=Gtk.MessageType.INFO,
                           buttons=Gtk.ButtonsType.OK, message_format=info)
    if detail is not None:
        md.format_secondary_text(detail)
    result = md.run()
    md.destroy()
    return result
