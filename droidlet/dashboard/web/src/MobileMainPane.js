/*
Copyright (c) Facebook, Inc. and its affiliates.
*/

import React from "react";

import { Container } from "react-bootstrap";

import NavbarComponent from "./components/NavbarComponent";
import MobileHomePane from "./components/MobileHomePane";
import MobileNavigationPane from "./components/MobileNavigationPane";
import MobileSettingsPane from "./components/MobileSettingsPane";

class MobileMainPane extends React.Component {
  constructor(props) {
    let width = window.innerWidth;
    super(props);
    this.state = {
      screen: "home",
      imageWidth: width / 2 - 25,
    };
  }

  paneHandler(pane) {
    this.setState({
      screen: pane,
    });
  }

  render() {
    let displayPane;
    if (this.state.screen === "home") {
      displayPane = <MobileHomePane imageWidth={this.state.imageWidth} />;
    } else if (this.state.screen === "navigation") {
      displayPane = <MobileNavigationPane imageWidth={this.state.imageWidth} />;
    } else {
      displayPane = <MobileSettingsPane imageWidth={this.state.imageWidth} />;
    }
    return (
      <Container fluid>
        {displayPane}
        <NavbarComponent paneHandler={this.paneHandler.bind(this)} />
      </Container>
    );
  }
}

export default MobileMainPane;
