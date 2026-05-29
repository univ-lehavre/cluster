#!/usr/bin/env perl
use strict;
use warnings;

my $input  = '.env';
my $output = '.env-example';

open my $in,  '<', $input  or die "Impossible d'ouvrir $input : $!\n";
open my $out, '>', $output or die "Impossible d'ouvrir $output : $!\n";

while (my $line = <$in>) {
    chomp $line;
    if ($line =~ /^\s*#|^\s*$/) {
        print $out "$line\n";
        next;
    } elsif ($line =~ /^([^=]+)=(.*)$/) {
        my ($key, $val) = ($1, $2);
        my $example;
            if ($val =~ /^\s*\d{1,3}(?:\.\d{1,3}){3}\s*(,\s*\d{1,3}(?:\.\d{1,3}){3}\s*)*$/) {
                $example = join(',', map { random_ip() } split(/\s*,\s*/, $val));
            } elsif ($val =~ m{^(?:/|\./|\.\./|~/?)[^\0]*$}) {
                $example = fake_path($val);
            } else {
                $example =
                    ($val =~ /^\d{1,3}(?:\.\d{1,3}){3}$/)                ? random_ip() :
                    ($val =~ /^[\w.%-]+\@[\w.-]+\.[A-Za-z]{2,}$/)        ? 'john.doe@example.com' :
                    ($val =~ /^\d+$/)                                      ? '42' :
                    ($val =~ /localhost|127\.0\.0\.1/)                   ? 'localhost' :
                    ($key =~ /MAIL|EMAIL/i)                                ? 'john.doe@example.com' :
                    ($key =~ /IP/i)                                        ? random_ip() :
                    ($key =~ /USER|LOGIN/i)                                ? 'bob' :
                    ($key =~ /PATH|DIR/i)                                  ? fake_path($val) :
                    ($key =~ /PORT/i)                                      ? '8080' :
                    ($key =~ /HOST/i)                                      ? 'localhost' :
                    ($key =~ /PWD|PASS|SECRET|TOKEN/i)                     ? 'changeme123' :
                    ($key =~ /ID|NUM|COUNT|NB|ENTIER/i)                    ? '42' :
                    'valeur_exemple';
        }
        print $out "$key=$example\n";
    } else {
        print $out "$line\n";
    }
}

close $in;
close $out;

sub fake_path {
    my ($val) = @_;
    my $ext = '';
    if ($val =~ m{(\.[a-zA-Z0-9]+)$}) {
        $ext = $1;
    }
        # known contient maintenant uniquement des segments de chemin
        my @known = qw(tmp log passwd shadow hosts hostname resolv.conf null zero random urandom bin etc usr var dev run cache python perl sh bash .ssh config);
        if ($val =~ m{^(/|~/?|\./|\.\./)}) {
            my $prefix = '';
            $prefix = $1 if $val =~ m{^(~/?|/|\./|\.\./)};
            my $path = $val;
            $path =~ s{^(~/?|/|\./|\.\./)}{};
            my @parts = split m{/}, $path;
            foreach my $i (0..$#parts) {
                my $found = 0;
                foreach my $std (@known) {
                    if ($parts[$i] eq $std) { $found = 1; last; }
                }
                $parts[$i] = 'exemple' unless $found;
            }
            my $fake = join('/', @parts);
            $fake = $prefix . $fake;
            $fake .= $ext if $ext && $fake !~ /\0$/;
            return $fake;
}
}

sub random_ip {
    return join('.', map { int(rand(223))+1 } 1..4);
}


